"""Verify administrator password setup without contacting hosted Auth."""
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import admin_setup


class AdminPasswordSetupTests(unittest.TestCase):
    email = 'admin@example.org'

    def client(self, role='admin', status='active'):
        client = MagicMock()
        client.auth.admin.list_users.return_value = [
            SimpleNamespace(id='admin-id', email=self.email, is_anonymous=False),
        ]
        client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
            'role': role, 'status': status,
        }
        return client

    def run_setup(self, client, *flags, passwords=()):
        output = io.StringIO()
        with patch('sys.argv', ['admin_setup.py', '--email', self.email, *flags]), \
                patch('admin_setup.get_supabase', return_value=client), \
                patch('admin_setup.getpass', side_effect=passwords) as prompt, \
                redirect_stdout(output), redirect_stderr(output):
            admin_setup.main()
        return output.getvalue(), prompt

    def test_dry_run_never_prompts_or_changes_auth(self):
        client = self.client()
        output, prompt = self.run_setup(client, '--set-password')
        self.assertIn('Dry run: set password', output)
        prompt.assert_not_called()
        client.auth.admin.update_user_by_id.assert_not_called()
        client.auth.admin.create_user.assert_not_called()
        client.table.return_value.insert.assert_not_called()

    def test_sets_only_selected_admin_password_and_audits_without_secret(self):
        client = self.client()
        password = 'private-password-for-test'
        output, prompt = self.run_setup(client, '--set-password', '--apply', passwords=(password, password))
        self.assertEqual(prompt.call_count, 2)
        client.auth.admin.update_user_by_id.assert_called_once_with('admin-id', {'password': password})
        client.auth.admin.create_user.assert_not_called()
        client.table.return_value.update.assert_not_called()
        audit = client.table.return_value.insert.call_args.args[0]
        self.assertEqual(audit['action'], 'admin.password.set')
        self.assertNotIn(password, str(audit))
        self.assertNotIn(password, output)

    def test_student_or_suspended_admin_cannot_be_reset(self):
        for role, status in [('student', 'active'), ('admin', 'suspended')]:
            with self.subTest(role=role, status=status):
                client = self.client(role, status)
                with self.assertRaises(SystemExit):
                    self.run_setup(client, '--set-password', '--apply')
                client.auth.admin.update_user_by_id.assert_not_called()
                client.table.return_value.update.assert_not_called()

    def test_invalid_confirmation_or_short_password_never_changes_auth(self):
        for passwords in [('valid-password-one', 'valid-password-two'), ('123456', '123456')]:
            with self.subTest(passwords=passwords):
                client = self.client()
                with self.assertRaises(SystemExit):
                    self.run_setup(client, '--set-password', '--apply', passwords=passwords)
                client.auth.admin.update_user_by_id.assert_not_called()
                client.table.return_value.insert.assert_not_called()

    def test_missing_account_is_not_created_by_password_setup(self):
        client = self.client()
        client.auth.admin.list_users.return_value = []
        with self.assertRaises(SystemExit):
            self.run_setup(client, '--set-password', '--apply')
        client.auth.admin.create_user.assert_not_called()
        client.auth.admin.update_user_by_id.assert_not_called()

    def test_explicit_demo_option_accepts_six_characters(self):
        client = self.client()
        output, _ = self.run_setup(client, '--set-password', '--allow-short-password', '--apply', passwords=('123456', '123456'))
        client.auth.admin.update_user_by_id.assert_called_once_with('admin-id', {'password': '123456'})
        self.assertNotIn('123456', output)

    def test_demo_option_still_rejects_shorter_or_mismatched_passwords(self):
        for passwords in [('12345', '12345'), ('123456', '654321')]:
            with self.subTest(passwords=passwords):
                client = self.client()
                with self.assertRaises(SystemExit):
                    self.run_setup(client, '--set-password', '--allow-short-password', '--apply', passwords=passwords)
                client.auth.admin.update_user_by_id.assert_not_called()
                client.table.return_value.insert.assert_not_called()

    def test_password_setup_finds_exact_email_beyond_first_page(self):
        client = self.client()
        others = [SimpleNamespace(id=f'other-{index}', email=f'other-{index}@example.org', is_anonymous=False) for index in range(100)]
        target = SimpleNamespace(id='selected-admin-id', email=self.email.upper(), is_anonymous=False)
        client.auth.admin.list_users.side_effect = [others, [target]]
        password = 'private-password-for-test'
        self.run_setup(client, '--set-password', '--apply', passwords=(password, password))
        client.auth.admin.update_user_by_id.assert_called_once_with('selected-admin-id', {'password': password})

    def test_provider_failure_does_not_expose_password_or_audit_success(self):
        client = self.client()
        password = 'private-password-for-test'
        client.auth.admin.update_user_by_id.side_effect = RuntimeError(f'provider request included {password}')
        output = io.StringIO()
        with patch('sys.argv', ['admin_setup.py', '--email', self.email, '--set-password', '--apply']), \
                patch('admin_setup.get_supabase', return_value=client), \
                patch('admin_setup.getpass', side_effect=(password, password)), \
                redirect_stdout(output), redirect_stderr(output), self.assertRaises(SystemExit):
            admin_setup.main()
        self.assertNotIn(password, output.getvalue())
        self.assertIn('Password update failed', output.getvalue())
        client.table.return_value.insert.assert_not_called()

    def test_reprovisioning_existing_account_keeps_password_and_explains_it(self):
        client = self.client()
        client.table.return_value.update.return_value.eq.return_value.select.return_value.execute.return_value.data = [
            {'user_id': 'admin-id', 'role': 'admin', 'status': 'active'},
        ]
        output, prompt = self.run_setup(client, '--create', '--apply')
        self.assertIn('password unchanged', output)
        prompt.assert_not_called()
        client.auth.admin.create_user.assert_not_called()
        client.auth.admin.update_user_by_id.assert_not_called()


if __name__ == '__main__':
    unittest.main()
