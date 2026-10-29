# Deploying Safari-Ops

Django 5.2 + MySQL 8, served by gunicorn behind nginx. Static files are served by WhiteNoise.

## First deploy
```bash
git clone <repo> /var/www/safariops && cd /var/www/safariops
python3 -m venv venv && venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env                     # SECRET_KEY, ALLOWED_HOSTS, SITE_URL, DB, email
mkdir -p logs backups media && chown -R www-data:www-data logs media
export DJANGO_SETTINGS_MODULE=config.settings.production
venv/bin/python manage.py check --deploy
venv/bin/python manage.py migrate
venv/bin/python manage.py createcachetable             # if CACHE_URL=dbcache://...
venv/bin/python manage.py collectstatic --noinput
```

### Bring data over from the legacy PHP app
Point the `LEGACY_DB_*` variables at the old database, then **either**:
- empty database: `manage.py import_legacy_data --dry-run`, then `manage.py import_legacy_data`
- already imported: `manage.py sync_legacy_data` (idempotent: settings, currencies, suppliers, staff, reviews, incidents, user permissions, passwords)

Legacy users keep their old passwords (bcrypt hashes are migrated and upgraded to PBKDF2 on first login).
Anyone else uses **Forgot your password?** on the login page, which needs working email settings.
To create the first owner by hand: `manage.py createsuperuser`, then set role = Owner under Settings → Users.

### Services
```bash
cp deploy/safariops.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now safariops
cp deploy/nginx.conf /etc/nginx/sites-available/safariops && ln -s ../sites-available/safariops /etc/nginx/sites-enabled/
certbot --nginx -d ops.example.com && systemctl reload nginx
crontab -u www-data deploy/crontab
```

## Updating
```bash
git pull && venv/bin/pip install -r requirements.txt
venv/bin/python manage.py migrate && venv/bin/python manage.py collectstatic --noinput
systemctl restart safariops
```

## Before go-live checklist
- [ ] `manage.py check --deploy` reports no issues
- [ ] Settings → General: app name, deposit %, VAT, bank details, emails are correct
- [ ] Deactivate test/QA accounts under Settings → Users
- [ ] Send yourself a password reset to prove outbound email works
- [ ] Never run `seed_demo_data` on production (it refuses unless `--allow-production`)

## Tests
`python manage.py test tests --settings=config.settings.test` (in-memory SQLite, no MySQL needed).
