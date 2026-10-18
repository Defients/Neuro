"""Credentials are read exclusively by the backend; diagnostics use an allowlist."""
import getpass
import os
import re
import sys

SERVICE = 'NeuralSignalStudio.Cortex'
SECRET_KEYS = re.compile(r'secret|token|client.?id|license.?id|password|username|email', re.I)
_sensitive: set[str] = set()


def remember(*values):
    _sensitive.update(str(v) for v in values if v)


def redact(value):
    if isinstance(value, dict):
        return {str(k): '[REDACTED]' if SECRET_KEYS.search(str(k)) else redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        for secret in sorted(_sensitive, key=len, reverse=True):
            value = value.replace(secret, '[REDACTED]')
        value = re.sub(r'(?i)(?:bearer\s+)[\w.\-]+', 'Bearer [REDACTED]', value)
        return value
    return value


def credentials():
    result = {}
    for field, env in [('clientId', 'NSS_CORTEX_CLIENT_ID'), ('clientSecret', 'NSS_CORTEX_CLIENT_SECRET'), ('license', 'NSS_CORTEX_LICENSE_ID')]:
        value = os.getenv(env)
        if not value:
            try:
                import keyring
                value = keyring.get_password(SERVICE, field)
            except Exception:
                value = None
        if value:
            result[field] = value
    remember(*result.values())
    return result


def configuration():
    c = credentials()
    return {'configured': bool(c.get('clientId') and c.get('clientSecret')), 'optional_license': bool(c.get('license')), 'storage': 'Windows Credential Manager or process environment', 'replacement_required': not bool(c.get('clientSecret'))}


if __name__ == '__main__':
    import keyring
    if '--clear' in sys.argv:
        for key in ('clientId', 'clientSecret', 'license'):
            try:
                keyring.delete_password(SERVICE, key)
            except keyring.errors.PasswordDeleteError:
                pass
        print('Local Cortex credentials removed.')
    else:
        print('Use a NEW client secret. Revoke the previously exposed secret in your EMOTIV developer account. Do not paste credentials into chat.')
        if input('Have you replaced the compromised secret? Type REPLACED: ').strip() != 'REPLACED':
            raise SystemExit('Configuration cancelled.')
        client = getpass.getpass('Client ID (hidden): ').strip()
        secret = getpass.getpass('Replacement client secret (hidden): ').strip()
        license_id = getpass.getpass('Optional developer license ID (Enter for automatic): ').strip()
        if not client or not secret:
            raise SystemExit('Both fields are required; nothing saved.')
        keyring.set_password(SERVICE, 'clientId', client)
        keyring.set_password(SERVICE, 'clientSecret', secret)
        if license_id:
            keyring.set_password(SERVICE, 'license', license_id)
        else:
            try:
                keyring.delete_password(SERVICE, 'license')
            except keyring.errors.PasswordDeleteError:
                pass
        print('Saved in the OS credential store. Restart the backend if already running.')
