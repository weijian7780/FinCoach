"""Trusted local provisioning. Passwords are prompted, never command arguments."""
import argparse
from getpass import getpass
from app.supabase_client import get_supabase


def prompt_password(parser, *, allow_short=False):
    """Keep passwords out of arguments, command history and terminal output."""
    # The shorter minimum is an explicit local-demo choice, never a default.
    minimum = 6 if allow_short else 12
    password = getpass(f'New admin password ({minimum}+ characters): ')
    confirmation = getpass('Confirm password: ')
    if len(password) < minimum or password != confirmation:
        parser.error(f'Use a matching password with at least {minimum} characters.')
    return password


def main():
    parser = argparse.ArgumentParser(description='Provision a dedicated FinCoach administrator; never exposes service keys.')
    parser.add_argument('--email', required=True, help='Email of the existing or new Supabase account')
    parser.add_argument('--create', action='store_true', help='Create a dedicated email/password account')
    parser.add_argument('--set-password', action='store_true', help='Set a password for an existing active administrator without changing its role')
    parser.add_argument('--allow-short-password', action='store_true', help='Allow 6+ characters for a local demo; Supabase password requirements still apply')
    parser.add_argument('--apply', action='store_true', help='Apply the requested account change (otherwise dry run)')
    args = parser.parse_args()
    if args.set_password and args.create:
        parser.error('Use --set-password for an existing administrator, or --create for a new account.')
    email = args.email.strip().lower()
    if '@' not in email:
        parser.error('A valid account email is required.')
    client = get_supabase()
    match = None
    page = 1
    while True:
        users = client.auth.admin.list_users(page=page, per_page=100)
        for user in users:
            if (user.email or '').lower() == email:
                match = user
        if match or len(users) < 100:
            break
        page += 1
    if args.set_password:
        if not match or match.is_anonymous:
            parser.error('An existing non-anonymous administrator account is required.')
        # Password setup must not promote a student account as a side effect.
        access = client.table('account_access').select('role,status').eq('user_id', str(match.id)).maybe_single().execute()
        if not access.data or access.data.get('role') != 'admin' or access.data.get('status') != 'active':
            parser.error('Password setup requires an existing active administrator.')
        if not args.apply:
            print(f'Dry run: set password for existing administrator: {email}')
            print('No changes made. Add --apply when ready.')
            return
        password = prompt_password(parser, allow_short=args.allow_short_password)
        try:
            client.auth.admin.update_user_by_id(str(match.id), {'password': password})
        except Exception:
            # Do not echo a provider exception that might contain request data.
            parser.error('Password update failed. Check Supabase Auth connectivity and password requirements.')
        client.table('admin_audit_logs').insert(dict(actor_id=str(match.id), action='admin.password.set', target_type='account', target_id=str(match.id), details={'method': 'trusted_local_setup'})).execute()
        print(f'Administrator password updated: {email}')
        return
    if not args.apply:
        print(f'Dry run: {"grant existing account" if match else "create dedicated account" if args.create else "account not found"}: {email}')
        print('No database changes made. Add --apply when ready.')
        return
    if match is None:
        if not args.create:
            parser.error('Account not found. Register first or use --create.')
        password = prompt_password(parser, allow_short=args.allow_short_password)
        result = client.auth.admin.create_user(dict(email=email, password=password, email_confirm=True, user_metadata={'full_name': 'Admin'}))
        match = result.user
    else:
        print('Existing account found; password unchanged. Use --set-password --apply to set one.')
    if not match or match.is_anonymous:
        parser.error('A non-anonymous verified account is required.')
    # Role/status are held in a protected table, not user-editable metadata.
    result = client.table('account_access').update({'role': 'admin', 'status': 'active'}).eq('user_id', str(match.id)).select('user_id,role,status').execute()
    if not result.data:
        parser.error('Access row missing. Apply the admin migration first.')
    client.table('admin_audit_logs').insert(dict(actor_id=str(match.id), action='admin.provision', target_type='account', target_id=str(match.id), details={'method': 'trusted_local_setup'})).execute()
    print(f'Administrator provisioned: {email}')
    print(f'Set ADMIN_LOGIN_EMAIL={email} in the server environment to enable the username alias admin.')


if __name__ == '__main__':
    main()
