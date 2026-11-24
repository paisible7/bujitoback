"""Patch Google auth fixes on VPS (create_user + GoogleLoginView)."""
import paramiko

HOST = "vps120167.serveur-vps.net"
USER = "root"
PASSWORD = "Z4Y7e3J94"

REMOTE = r'''
set -euo pipefail
cd /home/paisible/web/apibudig.capslockdev.com/public_html
if [[ -x venv/bin/python ]]; then PY=venv/bin/python; else PY=python3; fi

$PY <<'PY'
from pathlib import Path

models = Path('users/models.py')
text = models.read_text(encoding='utf-8')
old = """        apply_role_flags(user)
        user.set_password(password)
        user.save(using=self._db)
        return user"""
new = """        apply_role_flags(user)
        # Google / social : password=None → mot de passe inutilisable.
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user"""
if old in text:
    models.write_text(text.replace(old, new, 1), encoding='utf-8')
    print('models.py patched')
elif 'set_unusable_password()' in text and 'if password:' in text:
    print('models.py already patched')
else:
    print('models.py pattern not found')

views = Path('users/views.py')
v = views.read_text(encoding='utf-8')
old_v = """        if user is None:
            user = User.objects.create_user(
                email=email,
                password=None,
                role=ROLE_CLIENT,
                full_name=full_name,
                phone_number=None,
                city='',
            )
            user.set_unusable_password()
            user.is_active = True
            user.save()
            created = True
        else:"""
new_v = """        if user is None:
            try:
                user = User.objects.create_user(
                    email=email,
                    password=None,
                    role=ROLE_CLIENT,
                    full_name=full_name or '',
                    city='',
                )
            except Exception as exc:  # noqa: BLE001
                from django.db import IntegrityError

                if isinstance(exc, IntegrityError):
                    user = User.objects.filter(email__iexact=email).first()
                    if user is None:
                        return Response(
                            {'message': 'Impossible de créer le compte Google.'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    created = False
                else:
                    raise
            else:
                user.is_active = True
                user.save(update_fields=['is_active'])
                created = True
        else:"""
if old_v in v:
    views.write_text(v.replace(old_v, new_v, 1), encoding='utf-8')
    print('views.py patched')
elif 'Impossible de créer le compte Google' in v:
    print('views.py already patched')
else:
    print('views.py pattern not found')
    idx = v.find('if user is None:')
    print(repr(v[idx:idx+450]) if idx >= 0 else 'missing')

env = Path('.env')
env_txt = env.read_text(encoding='utf-8') if env.exists() else ''
ios = '678162722463-vp7ut7798a01a42g25a8qkmr4pt2po53.apps.googleusercontent.com'
if 'GOOGLE_OAUTH_CLIENT_IDS=' in env_txt and ios not in env_txt:
    lines = []
    for line in env_txt.splitlines():
        if line.startswith('GOOGLE_OAUTH_CLIENT_IDS='):
            val = line.split('=', 1)[1].strip().strip('"').strip("'")
            ids = [x.strip() for x in val.split(',') if x.strip()]
            if ios not in ids:
                ids.append(ios)
            line = 'GOOGLE_OAUTH_CLIENT_IDS=' + ','.join(ids)
            print('env ios client added')
        lines.append(line)
    env.write_text('\n'.join(lines) + '\n', encoding='utf-8')
else:
    print('env ios ok or missing key')
PY

systemctl restart bujito_backend.service
sleep 2
systemctl is-active bujito_backend.service
'''

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=60)
_, stdout, stderr = client.exec_command(REMOTE, timeout=120)
print(stdout.read().decode('utf-8', errors='replace'))
err = stderr.read().decode('utf-8', errors='replace')
if err.strip():
    print('STDERR:', err[-2000:])
print('exit', stdout.channel.recv_exit_status())
client.close()
