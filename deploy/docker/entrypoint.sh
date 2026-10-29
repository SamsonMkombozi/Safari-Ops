#!/bin/sh
# Container roles: web (migrate + collectstatic + gunicorn) | scheduler (cron-style loop) | any manage.py command
set -e

wait_for_db() {
  i=0
  until python -c "import django; django.setup(); from django.db import connection; connection.ensure_connection()" 2>/dev/null; do
    i=$((i+1)); [ $i -gt 60 ] && echo "database not reachable" && exit 1
    echo "waiting for database… ($i)"; sleep 2
  done
}

case "$1" in
  web)
    wait_for_db
    python manage.py migrate --noinput
    python manage.py createcachetable
    python manage.py collectstatic --noinput -v0
    exec gunicorn -c deploy/gunicorn.conf.py config.wsgi
    ;;
  scheduler)
    wait_for_db
    # The web container owns migrations — don't run jobs against a half-migrated schema.
    until python manage.py migrate --check >/dev/null 2>&1; do echo "waiting for migrations…"; sleep 5; done
    # Same jobs as deploy/crontab: email queue every 2 min, reminders/quote expiry every 15, cleanup nightly.
    n=0
    while true; do
      python manage.py process_email_queue || true
      if [ $((n % 8)) -eq 0 ]; then python manage.py process_reminders || true; fi
      if [ $((n % 720)) -eq 0 ]; then python manage.py clearsessions || true; python manage.py flushexpiredtokens || true; fi
      n=$((n+1)); sleep 120
    done
    ;;
  *)
    exec python manage.py "$@"
    ;;
esac
