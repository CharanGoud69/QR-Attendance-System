"""Standalone ClassLedger. No ChatGPT or external identity service required."""
import csv, functools, hashlib, io, os, secrets, sqlite3, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
import qrcode
from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash

IST=timezone(timedelta(hours=5,minutes=30))
SCHEMA='''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, name TEXT NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','student')), batch TEXT NOT NULL DEFAULT '', joined TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1, force_change INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS windows(id TEXT PRIMARY KEY, token TEXT UNIQUE NOT NULL, batch TEXT NOT NULL, day TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('IN','OUT')), created REAL NOT NULL, expires REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS scans(user_id INTEGER NOT NULL REFERENCES users(id),day TEXT NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('IN','OUT')),at REAL NOT NULL,window_id TEXT NOT NULL REFERENCES windows(id),PRIMARY KEY(user_id,day,kind));
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,count INTEGER NOT NULL,until REAL NOT NULL);
'''

def create_app(test_config=None):
    app=Flask(__name__)
    folder=Path(os.environ.get('DATA_DIR',Path(__file__).parent/'data'))
    app.config.update(DATA_DIR=str(folder),DATABASE=str(folder/'attendance.db'),SECRET_KEY=os.environ.get('SECRET_KEY'),SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE','0')=='1',PERMANENT_SESSION_LIFETIME=timedelta(days=14),MAX_CONTENT_LENGTH=1024*1024,CLOCK=time.time)
    if test_config: app.config.update(test_config)
    Path(app.config['DATA_DIR']).mkdir(parents=True,exist_ok=True)
    if not app.config['SECRET_KEY']:
        key=Path(app.config['DATA_DIR'])/'secret.key'
        try:
            with key.open('x') as f:f.write(secrets.token_hex(32))
            key.chmod(0o600)
        except FileExistsError:pass
        app.config['SECRET_KEY']=key.read_text().strip()
    def db():
        if 'db' not in g:
            g.db=sqlite3.connect(app.config['DATABASE'],timeout=15)
            g.db.row_factory=sqlite3.Row
            g.db.execute('PRAGMA foreign_keys=ON')
        return g.db
    def now():return app.config['CLOCK']()
    def day():return datetime.fromtimestamp(now(),IST).date().isoformat()
    def safe_next(value):
        p=urlsplit(value or '/')
        return value if value and value.startswith('/') and not value.startswith('//') and not p.netloc and not p.scheme and '\\' not in value else '/'
    def login_required(role=None):
        def decorator(fn):
            @functools.wraps(fn)
            def wrapped(*a,**kw):
                if not g.user:return redirect(url_for('login',next=request.full_path))
                if role and g.user['role']!=role:abort(403)
                return fn(*a,**kw)
            return wrapped
        return decorator
    def csrf():
        if 'csrf' not in session:session['csrf']=secrets.token_urlsafe(32)
        return session['csrf']
    @app.before_request
    def protect():
        g.user=None
        if session.get('uid'):
            u=db().execute('SELECT * FROM users WHERE id=?',(session['uid'],)).fetchone()
            if u and not u['archived'] and u['version']==session.get('version'):g.user=u
            else:session.clear()
        if request.method=='POST' and not secrets.compare_digest(request.form.get('csrf',''),session.get('csrf','!')):abort(400,'Form expired. Reload the page and try again.')
        if g.user and g.user['force_change'] and request.endpoint not in ('password','logout','static'):
            return redirect(url_for('password',next=safe_next(request.full_path)))
    @app.after_request
    def headers(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='no-referrer'
        return response
    @app.teardown_appcontext
    def close(_):
        conn=g.pop('db',None)
        if conn:conn.close()
    @app.context_processor
    def context():return dict(csrf=csrf,today=day(),clock=now(),user=g.user)
    @app.template_filter('ist')
    def ist(value):return datetime.fromtimestamp(value,IST).strftime('%I:%M:%S %p') if value else '—'
    with app.app_context():
        db().executescript(SCHEMA);db().commit()
    @app.get('/health')
    def health():return {'status':'ok'}
    @app.route('/login',methods=['GET','POST'])
    def login():
        target=safe_next(request.values.get('next','/'))
        if g.user:return redirect(target if target!='/login' else '/')
        if request.method=='POST':
            username=request.form.get('username','').strip().lower()[:100]
            keys=[hashlib.sha256(v.encode()).hexdigest() for v in ['user:'+username,'ip:'+(request.remote_addr or '')]]
            limits=[8,40]
            locked=False
            for key,limit in zip(keys,limits):
                row=db().execute('SELECT * FROM attempts WHERE key=?',(key,)).fetchone()
                if row and row['until']>now() and row['count']>=limit:locked=True
            if locked:flash('Too many attempts. Try again in 15 minutes.','error');return render_template('login.html',target=target),429
            u=db().execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
            valid=check_password_hash(u['password'] if u else app.config['DUMMY_HASH'],request.form.get('password',''))
            if u and valid and not u['archived']:
                for key in keys:db().execute('DELETE FROM attempts WHERE key=?',(key,))
                db().commit();session.clear();session.update(uid=u['id'],version=u['version']);session.permanent=request.form.get('remember')=='yes'
                return redirect(target)
            for key in keys:
                db().execute('INSERT INTO attempts VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN until<=? THEN 1 ELSE count+1 END,until=CASE WHEN until<=? THEN excluded.until ELSE until END',(key,now()+900,now(),now()))
            db().commit();flash('Incorrect ID or password, or this account is inactive.','error')
        has_admin=db().execute("SELECT 1 FROM users WHERE role='admin'").fetchone()
        return render_template('login.html',target=target,has_admin=has_admin)
    @app.post('/logout')
    def logout():session.clear();return redirect('/login')
    @app.route('/password',methods=['GET','POST'])
    @login_required()
    def password():
        target=safe_next(request.values.get('next','/'))
        if request.method=='POST':
            new=request.form.get('new','')
            if not check_password_hash(g.user['password'],request.form.get('current','')):flash('Current password is incorrect.','error')
            elif len(new)<8 or len(new)>128:flash('Use 8–128 characters for the new password.','error')
            elif new!=request.form.get('confirm'):flash('New passwords do not match.','error')
            elif check_password_hash(g.user['password'],new):flash('Choose a different password.','error')
            else:
                db().execute('UPDATE users SET password=?,version=version+1,force_change=0 WHERE id=?',(generate_password_hash(new),g.user['id']));db().commit();session['version']=g.user['version']+1
                flash('Password updated. Other signed-in sessions were logged out.','success');return redirect(target)
        return render_template('password.html',target=target)
    @app.get('/')
    @login_required()
    def index():
        if g.user['role']=='admin':return redirect('/admin')
        rows=db().execute('SELECT day,MAX(CASE WHEN kind=\'IN\' THEN at END) AS arrival,MAX(CASE WHEN kind=\'OUT\' THEN at END) AS departure FROM scans WHERE user_id=? GROUP BY day ORDER BY day DESC',(g.user['id'],)).fetchall()
        return render_template('student.html',rows=rows)
    def students():return db().execute("SELECT * FROM users WHERE role='student' ORDER BY name").fetchall()
    def register(batch,date):
        people=[s for s in students() if (not batch or s['batch']==batch) and s['joined']<=date]
        result=[]
        for s in people:
            scans=db().execute('SELECT kind,at FROM scans WHERE user_id=? AND day=?',(s['id'],date)).fetchall();times={x['kind']:x['at'] for x in scans}
            closed=db().execute("SELECT 1 FROM windows WHERE batch=? AND day=? AND kind='OUT' AND revoked=0 AND expires<=?",(s['batch'],date,now())).fetchone()
            status='Complete' if len(times)==2 else 'Missing checkout' if times.get('IN') else 'Absent' if closed else 'Not marked'
            result.append(dict(s,arrival=times.get('IN'),departure=times.get('OUT'),status=status))
        return result
    @app.get('/admin')
    @login_required('admin')
    def admin():
        batch=request.args.get('batch','');date=request.args.get('date',day())
        try:datetime.strptime(date,'%Y-%m-%d')
        except ValueError:abort(400)
        people=students();batches=sorted({s['batch'] for s in people if not s['archived']});batch=batch or (batches[0] if batches else '')
        windows=db().execute('SELECT * FROM windows WHERE batch=? AND day=? ORDER BY created DESC',(batch,day())).fetchall()
        return render_template('admin.html',people=people,batches=batches,batch=batch,date=date,rows=register(batch,date),windows=windows)
    @app.route('/admin/students',methods=['GET','POST'])
    @login_required('admin')
    def manage_students():
        if request.method=='POST':
            name=request.form.get('name','').strip();username=request.form.get('username','').strip().lower();batch=request.form.get('batch','').strip();pwd=request.form.get('password','')
            if not all([name,username,batch]) or any(len(v)>100 for v in [name,username,batch]) or not 8<=len(pwd)<=128:flash('Fill every field. Password must be 8–128 characters.','error')
            else:
                try:
                    db().execute("INSERT INTO users(username,name,password,role,batch,joined,force_change) VALUES(?,?,?,'student',?,?,1)",(username,name,generate_password_hash(pwd),batch,day()));db().commit();flash('Student added. Share their ID and temporary password privately.','success');return redirect('/admin/students')
                except sqlite3.IntegrityError:db().rollback();flash('That student ID already exists.','error')
        return render_template('students.html',people=students())
    @app.post('/admin/student/<int:uid>')
    @login_required('admin')
    def manage_student(uid):
        u=db().execute("SELECT * FROM users WHERE id=? AND role='student'",(uid,)).fetchone()
        if not u:abort(404)
        if request.form.get('action')=='archive':db().execute('UPDATE users SET archived=?,version=version+1 WHERE id=?',(0 if u['archived'] else 1,uid))
        elif request.form.get('action')=='reset':
            pwd=request.form.get('password','')
            if not 8<=len(pwd)<=128:flash('Temporary password must be 8–128 characters.','error');return redirect('/admin/students')
            db().execute('UPDATE users SET password=?,force_change=1,version=version+1 WHERE id=?',(generate_password_hash(pwd),uid))
        else:abort(400)
        db().commit();flash('Student account updated. Existing sessions were logged out.','success');return redirect('/admin/students')
    @app.post('/admin/generate')
    @login_required('admin')
    def generate():
        batch=request.form.get('batch','');kind=request.form.get('kind')
        if kind not in ('IN','OUT') or not db().execute("SELECT 1 FROM users WHERE role='student' AND archived=0 AND batch=?",(batch,)).fetchone():abort(400)
        if kind=='OUT' and not db().execute("SELECT 1 FROM windows WHERE batch=? AND day=? AND kind='IN'",(batch,day())).fetchone():flash('Generate the IN QR before the OUT QR.','error');return redirect('/admin')
        db().execute('BEGIN IMMEDIATE');created=now();wid=secrets.token_urlsafe(12);token=secrets.token_urlsafe(32)
        db().execute('UPDATE windows SET revoked=1 WHERE batch=? AND day=? AND kind=?',(batch,day(),kind))
        db().execute('INSERT INTO windows(id,token,batch,day,kind,created,expires) VALUES(?,?,?,?,?,?,?)',(wid,token,batch,day(),kind,created,created+600));db().commit()
        return redirect(url_for('window',wid=wid))
    def base_url():
        configured=os.environ.get('PUBLIC_BASE_URL')
        row=db().execute("SELECT value FROM settings WHERE key='base_url'").fetchone()
        return (configured or (row['value'] if row else '') or request.host_url).rstrip('/')
    def get_window(wid):
        w=db().execute('SELECT * FROM windows WHERE id=?',(wid,)).fetchone()
        if not w:abort(404)
        return w
    @app.get('/admin/qr/<wid>')
    @login_required('admin')
    def window(wid):
        w=get_window(wid);link=base_url()+url_for('scan',token=w['token'])
        return render_template('qr.html',w=w,link=link,local=urlsplit(link).hostname in ('localhost','127.0.0.1','0.0.0.0'))
    @app.get('/admin/qr/<wid>.png')
    @login_required('admin')
    def qr_image(wid):
        w=get_window(wid);buf=io.BytesIO();qrcode.make(base_url()+url_for('scan',token=w['token'])).save(buf,format='PNG');buf.seek(0)
        return send_file(buf,mimetype='image/png',as_attachment=request.args.get('download')=='1',download_name=f"ClassLedger-{w['kind']}-{w['day']}.png")
    @app.post('/admin/qr/<wid>/cancel')
    @login_required('admin')
    def cancel(wid):
        get_window(wid);db().execute('UPDATE windows SET revoked=1 WHERE id=?',(wid,));db().commit();flash('QR cancelled immediately.','success');return redirect(url_for('window',wid=wid))
    @app.route('/check-in/<token>',methods=['GET','POST'])
    @login_required('student')
    def scan(token):
        conn=db()
        if request.method=='POST':conn.execute('BEGIN IMMEDIATE')
        fresh=conn.execute('SELECT archived,version FROM users WHERE id=?',(g.user['id'],)).fetchone()
        if not fresh or fresh['archived'] or fresh['version']!=session.get('version'):abort(403)
        timestamp=now();w=conn.execute('SELECT * FROM windows WHERE token=?',(token,)).fetchone()
        if not w:abort(404)
        saved=conn.execute('SELECT at FROM scans WHERE user_id=? AND day=? AND kind=?',(g.user['id'],w['day'],w['kind'])).fetchone()
        error=None
        if g.user['batch']!=w['batch']:error='This QR belongs to another batch.'
        elif w['day']<g.user['joined']:error='This class took place before your enrolment.'
        elif not saved and (w['revoked'] or timestamp>=w['expires'] or w['day']!=day()):error='This QR has expired or was cancelled. Ask sir for a fresh QR.'
        elif not saved and w['kind']=='OUT' and not conn.execute("SELECT 1 FROM scans WHERE user_id=? AND day=? AND kind='IN'",(g.user['id'],w['day'])).fetchone():error='IN is missing. Check in before checking out.'
        if request.method=='POST':
            if not error and not saved:
                conn.execute('INSERT INTO scans VALUES(?,?,?,?,?)',(g.user['id'],w['day'],w['kind'],timestamp,w['id']));conn.commit();flash(f"{w['kind']} attendance saved.",'success');return redirect(request.path)
            conn.rollback()
        return render_template('scan.html',w=w,saved=saved,error=error)
    @app.route('/admin/settings',methods=['GET','POST'])
    @login_required('admin')
    def settings():
        if request.method=='POST':
            value=request.form.get('base_url','').strip().rstrip('/');p=urlsplit(value)
            if p.scheme not in ('http','https') or not p.netloc or p.username or p.password or p.query or p.fragment or p.path:flash('Use a root URL, e.g. http://192.168.1.5:8000 or https://your-domain.example','error')
            else:
                db().execute("INSERT INTO settings VALUES('base_url',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(value,));db().commit();flash('QR website address updated. Download a fresh image for active QRs.','success')
        return render_template('settings.html',base=base_url())
    @app.get('/admin/export')
    @login_required('admin')
    def export():
        month=request.args.get('month','');date=request.args.get('date',day());batch=request.args.get('batch','')
        if month:
            try:datetime.strptime(month,'%Y-%m')
            except ValueError:abort(400)
            dates=[r['day'] for r in db().execute('SELECT DISTINCT day FROM windows WHERE day LIKE ? ORDER BY day',(month+'-%',))]
        else:
            try:datetime.strptime(date,'%Y-%m-%d')
            except ValueError:abort(400)
            dates=[date]
        buf=io.StringIO();writer=csv.writer(buf);writer.writerow(['Student ID','Name','Batch','Date','IN (IST)','OUT (IST)','Status'])
        for d in dates:
            for r in register(batch,d):
                values=[r['username'],r['name'],r['batch'],d,ist(r['arrival']),ist(r['departure']),r['status']]
                writer.writerow(["'"+v if v.startswith(('=','+','-','@','\t','\r')) else v for v in values])
        return app.response_class('\ufeff'+buf.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename="ClassLedger-{month or date}.csv"'})
    @app.get('/admin/backup')
    @login_required('admin')
    def backup():
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'backup.db';target=sqlite3.connect(path);db().backup(target);target.close();data=path.read_bytes()
        return send_file(io.BytesIO(data),mimetype='application/octet-stream',as_attachment=True,download_name='ClassLedger-backup.db')
    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def problem(e):return render_template('error.html',code=e.code,message=e.description),e.code
    app.config['DUMMY_HASH']=generate_password_hash(secrets.token_urlsafe(24))
    return app

if __name__=='__main__':
    from waitress import serve
    app=create_app();port=int(os.environ.get('PORT','8000'))
    print(f'ClassLedger running on port {port}. Open http://localhost:{port}')
    serve(app,host='0.0.0.0',port=port)
