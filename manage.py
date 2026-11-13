"""Run locally on the server: python manage.py init-admin. Passwords are never arguments."""
import argparse,getpass
from workspace_app import data_directory,store
from workspace_app.security import create_user
from workspace_app.backup import workspace_lock

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['init-admin']);args=parser.parse_args()
    root=data_directory()
    with workspace_lock(root):
        from workspace_app.isolation import check_database
        check_database(root)
        with store.connect(root) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM users LIMIT 1').fetchone():parser.exit(1,'An administrator already exists. Use Accounts to reset/create users.\n')
            username=input('Initial administrator username: ')
            password=getpass.getpass('Password (at least 12 characters): ')
            if password!=getpass.getpass('Confirm password: '):parser.exit(1,'Passwords did not match.\n')
            create_user(db,username,password,'Administrator',initial=True)
        print('Administrator created. Existing records assigned privately to this account. Start the application and log in.')
