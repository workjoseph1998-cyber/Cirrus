"""Synthetic credentials for temporary browser-test databases only."""
from workspace_app import store,security
PASSWORD='Browser-tests-only-password-2026!'
def bootstrap(root):
    store.migrate(root)
    with store.connect(root) as db:
        if not db.execute('SELECT 1 FROM users LIMIT 1').fetchone():security.create_user(db,'browser-admin',PASSWORD,'Administrator',True)
def login(page,base):
    page.goto(base+'/login');page.get_by_label('Username',exact=True).fill('browser-admin');page.get_by_label('Password',exact=True).fill(PASSWORD);page.get_by_role('button',name='Sign in',exact=True).click();page.wait_for_url(base+'/')
