"""Run locally/through a hosting shell; there is no public account setup endpoint."""
import argparse,getpass,sqlite3
from datetime import datetime
from app import create_app,IST
from werkzeug.security import generate_password_hash

def main():
    p=argparse.ArgumentParser();p.add_argument('--ensure',action='store_true');p.add_argument('--reset',action='store_true');args=p.parse_args()
    app=create_app();db=sqlite3.connect(app.config['DATABASE'])
    exists=db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone()
    if args.ensure and exists:print('Admin is already configured.');return
    print('Create an admin account (or use --reset for an existing admin).')
    username=input('Admin ID: ').strip().lower();name=input('Name: ').strip()
    pwd=getpass.getpass('Password (8+ characters): ');again=getpass.getpass('Confirm password: ')
    if not username or len(username)>100 or not name or len(name)>100 or not 8<=len(pwd)<=128 or pwd!=again:raise SystemExit('Invalid details or passwords do not match. Please run setup again.')
    existing=db.execute('SELECT role FROM users WHERE username=?',(username,)).fetchone()
    if existing:
        if not args.reset or existing[0]!='admin':raise SystemExit('ID exists. Use --reset only for an existing admin.')
        db.execute('UPDATE users SET password=?,version=version+1,force_change=0 WHERE username=?',(generate_password_hash(pwd),username))
    else:db.execute("INSERT INTO users(username,name,password,role,joined) VALUES(?,?,?,'admin',?)",(username,name,generate_password_hash(pwd),datetime.now(IST).date().isoformat()))
    db.commit();db.close();print('Admin ready. Start the app and sign in with this ID.')
if __name__=='__main__':main()
