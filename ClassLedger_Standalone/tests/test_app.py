import sqlite3
import pytest
from werkzeug.security import generate_password_hash
from app import create_app

@pytest.fixture
def state(tmp_path):
    clock=[1792231200.0]
    app=create_app({'TESTING':True,'DATA_DIR':str(tmp_path),'DATABASE':str(tmp_path/'test.db'),'SECRET_KEY':'test-only-key','CLOCK':lambda:clock[0]})
    db=sqlite3.connect(app.config['DATABASE']);db.row_factory=sqlite3.Row
    for username,role,batch in [('sir','admin',''),('s1','student','A'),('s2','student','A'),('s3','student','B')]:
        db.execute('INSERT INTO users(username,name,password,role,batch,joined) VALUES(?,?,?,?,?,?)',(username,username,generate_password_hash('Password123'),role,batch,'2026-10-01'))
    db.commit()
    yield app,db,clock
    db.close()

def post(client,url,data=None):
    with client.session_transaction() as s:s.setdefault('csrf','test-csrf');token=s['csrf']
    return client.post(url,data={'csrf':token,**(data or {})})
def login(app,username):
    c=app.test_client();assert post(c,'/login',{'username':username,'password':'Password123','remember':'yes'}).status_code==302;return c
def generate(admin,db,kind='IN',batch='A'):
    assert post(admin,'/admin/generate',{'kind':kind,'batch':batch}).status_code==302
    return db.execute('SELECT * FROM windows ORDER BY rowid DESC LIMIT 1').fetchone()

def test_admin_pages_and_qr_image(state):
    app,db,_=state;a=login(app,'sir')
    for url in ['/admin','/admin/students','/admin/settings','/password']:assert a.get(url).status_code==200
    w=generate(a,db);assert a.get('/admin/qr/'+w['id']).status_code==200
    png=a.get('/admin/qr/'+w['id']+'.png');assert png.status_code==200 and png.data.startswith(b'\x89PNG')
    assert a.get('/admin/export?month=2026-10').status_code==200
    assert a.get('/admin/backup').data.startswith(b'SQLite format 3')

def test_no_external_auth_redirect(state):
    app,_,_=state;c=app.test_client();r=c.get('/check-in/test-token');assert '/login?' in r.location and 'chatgpt' not in r.location
    assert b'No ChatGPT account needed' in c.get('/login').data

def test_in_out_and_duplicates(state):
    app,db,clock=state;a=login(app,'sir');s=login(app,'s1');w=generate(a,db)
    assert s.get('/check-in/'+w['token']).status_code==200
    assert post(s,'/check-in/'+w['token']).status_code==302
    first=db.execute('SELECT at FROM scans').fetchone()[0];clock[0]+=20
    post(s,'/check-in/'+w['token']);assert db.execute('SELECT count(*),at FROM scans').fetchone()[:]==(1,first)
    out=generate(a,db,'OUT');post(s,'/check-in/'+out['token']);assert db.execute('SELECT count(*) FROM scans').fetchone()[0]==2
    assert b'Complete' in s.get('/').data

def test_expired_at_exact_boundary(state):
    app,db,clock=state;a=login(app,'sir');s=login(app,'s1');w=generate(a,db);clock[0]=w['expires']
    assert b'expired' in post(s,'/check-in/'+w['token']).data
    assert db.execute('SELECT count(*) FROM scans').fetchone()[0]==0

def test_cancel_and_regenerate(state):
    app,db,_=state;a=login(app,'sir');s=login(app,'s1');old=generate(a,db);fresh=generate(a,db)
    post(s,'/check-in/'+old['token']);assert db.execute('SELECT count(*) FROM scans').fetchone()[0]==0
    post(a,'/admin/qr/'+fresh['id']+'/cancel');post(s,'/check-in/'+fresh['token']);assert db.execute('SELECT count(*) FROM scans').fetchone()[0]==0

def test_wrong_batch_and_out_without_in(state):
    app,db,_=state;a=login(app,'sir');w=generate(a,db);wrong=login(app,'s3')
    assert b'another batch' in post(wrong,'/check-in/'+w['token']).data
    out=generate(a,db,'OUT');s=login(app,'s1');assert b'IN is missing' in post(s,'/check-in/'+out['token']).data
    assert db.execute('SELECT count(*) FROM scans').fetchone()[0]==0

def test_student_isolation_and_admin_denied(state):
    app,db,_=state;a=login(app,'sir');w=generate(a,db);s=login(app,'s1');post(s,'/check-in/'+w['token']);other=login(app,'s2')
    assert b'No scans recorded yet' in other.get('/').data
    for path in ['/admin','/admin/students','/admin/backup','/admin/qr/'+w['id']+'.png','/admin/export']:
        assert s.get(path).status_code==403
    assert post(s,'/admin/generate',{'kind':'IN','batch':'A'}).status_code==403

def test_csrf_and_open_redirect(state):
    app,_,_=state;c=app.test_client();assert c.post('/login',data={'username':'sir','password':'Password123'}).status_code==400
    r=post(c,'/login',{'username':'sir','password':'Password123','next':'https://evil.example'});assert r.location=='/'

def test_archive_and_password_reset_revoke_sessions(state):
    app,db,_=state;a=login(app,'sir');s=login(app,'s1');uid=db.execute("SELECT id FROM users WHERE username='s1'").fetchone()[0]
    post(a,f'/admin/student/{uid}',{'action':'reset','password':'Temporary987'});assert s.get('/').status_code==302
    c=app.test_client();post(c,'/login',{'username':'s1','password':'Temporary987'});assert '/password' in c.get('/').location
    post(c,'/password',{'current':'Temporary987','new':'MyNewPass123','confirm':'MyNewPass123'});assert c.get('/').status_code==200
    post(a,f'/admin/student/{uid}',{'action':'archive'});assert c.get('/').status_code==302

def test_login_rate_limit(state):
    app,_,_=state;c=app.test_client()
    for _ in range(8):post(c,'/login',{'username':'s1','password':'wrong'})
    assert post(c,'/login',{'username':'s1','password':'wrong'}).status_code==429

def test_add_unique_student_and_safe_csv(state):
    app,db,_=state;a=login(app,'sir');data={'username':'s4','name':'=DANGEROUS','batch':'A','password':'Temporary987'}
    assert post(a,'/admin/students',data).status_code==302
    assert b'already exists' in post(a,'/admin/students',data).data
    assert b"'=DANGEROUS" in a.get('/admin/export').data

def test_absent_after_out_window_closes(state):
    app,db,clock=state;a=login(app,'sir');generate(a,db);out=generate(a,db,'OUT');clock[0]=out['expires']
    assert b'Absent' in a.get('/admin?batch=A').data
