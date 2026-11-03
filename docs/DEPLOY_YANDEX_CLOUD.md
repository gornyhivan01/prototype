# Деплой Prototype в Yandex Cloud (одна VM)

Инструкция для варианта «всё на одной VM»: PostgreSQL, Keycloak, FastAPI и
Caddy в Docker Compose. Домен не покупаем — используем бесплатный
`sslip.io`, чтобы получить настоящий TLS-сертификат Let's Encrypt.

```text
            Интернет :80/:443
                    │
        ┌───────────▼────────────┐
        │ VM Ubuntu 24.04        │
        │ 2 vCPU / 4 ГБ / 50 ГБ  │
        │                        │
        │  Caddy ──► app:8000    │
        │        └─► keycloak:8080│
        │  PostgreSQL (volume)   │
        └────────────────────────┘
```

## 0. Что понадобится

- аккаунт Yandex Cloud с платёжным аккаунтом;
- `yc` CLI и SSH-ключ;
- публичный IP VM (статический рекомендуется);
- 15–30 минут.

Ориентир по стоимости: **~1,7–3,5 тыс. ₽/мес** (VM 2 vCPU/4 ГБ + диск 50 ГБ
+ статический IP). Точную сумму покажет калькулятор Yandex Cloud.

## 1. Сеть, IP и security group

```bash
yc config set cloud-id <cloud-id>
yc config set folder-id <folder-id>

yc vpc network create --name prototype-net
yc vpc subnet create --name prototype-subnet \
  --network-name prototype-net --zone ru-central1-a --range 10.10.0.0/24

yc vpc security-group create --name prototype-sg --network-name prototype-net
```

Правила (22 — только ваш IP, 80/443 — всем, исходящий — всё):

```bash
SG=prototype-sg
yc vpc security-group update-rules $SG --add-rule \
  "direction=ingress,port=22,protocol=tcp,v4-cidrs=[<ВАШ_IP>/32]"
yc vpc security-group update-rules $SG --add-rule \
  "direction=ingress,port=80,protocol=tcp,v4-cidrs=[0.0.0.0/0]"
yc vpc security-group update-rules $SG --add-rule \
  "direction=ingress,port=443,protocol=tcp,v4-cidrs=[0.0.0.0/0]"
yc vpc security-group update-rules $SG --add-rule \
  "direction=ingress,port=443,protocol=udp,v4-cidrs=[0.0.0.0/0]"
yc vpc security-group update-rules $SG --add-rule \
  "direction=egress,port=any,protocol=any,v4-cidrs=[0.0.0.0/0]"
```

Статический IP:

```bash
yc vpc address create --name prototype-ip --external-ipv4 zone=ru-central1-a
```

## 2. VM

```bash
yc compute instance create \
  --name prototype-vm \
  --zone ru-central1-a \
  --network-interface subnet-name=prototype-subnet,nat-ip-version=ipv4,security-group-ids=<SG_ID> \
  --create-boot-disk image-family=ubuntu-2404-lts,size=50GB,type=network-ssd \
  --cores 2 --memory 4G \
  --metadata-from-file ssh-keys=$HOME/.ssh/id_ed25519.pub
```

Привяжите к VM зарезервированный IP (в консоли: «Сеть» → «Публичный IP»,
или через `yc compute instance update ... --nat-address <IP>`; флаги
уточните в `yc compute instance update --help`).

Запишите публичный IP — он понадобится для адресов `sslip.io`:

```text
APP_HOST=app.<IP>.sslip.io
AUTH_HOST=auth.<IP>.sslip.io
```

`sslip.io` — публичный DNS-сервис: имя `app.203.0.113.10.sslip.io`
автоматически резолвится в `203.0.113.10`. Покупать домен не нужно, а Caddy
сможет выпустить обычный сертификат Let's Encrypt.

> Если `sslip.io` недоступен из вашей сети, есть запасной вариант —
> HTTP без TLS (см. раздел 9). Для SSO и нормальной работы лучше TLS.

## 3. Docker на VM

```bash
ssh ubuntu@<IP>

curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker          # или перелогиниться

sudo apt-get update && sudo apt-get install -y git
```

Опционально закройте лишнее локальным firewall (облачная security group уже
ограничивает доступ):

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## 4. Код и конфиг

```bash
sudo mkdir -p /opt/prototype && sudo chown $USER /opt/prototype
git clone git@github.com:gornyhivan01/prototype.git /opt/prototype
cd /opt/prototype

cp deploy/.env.prod.example .env
chmod 600 .env
nano .env
```

В `.env` обязательно замените:

- `PUBLIC_IP`, `APP_HOST`, `AUTH_HOST`, `APP_URL`, `AUTH_URL`;
- `POSTGRES_PASSWORD`, `KEYCLOAK_DB_PASSWORD` — `openssl rand -hex 32`;
- `SECRET_KEY` — `openssl rand -hex 32`;
- `KEYCLOAK_CLIENT_SECRET` — `openssl rand -hex 32`;
- `KEYCLOAK_ADMIN_PASSWORD` — сильный пароль (это master-админ Keycloak);
- `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` — первый админ приложения.

Пароли — только hex/alphanumeric: они подставляются в SQL и в URL.

## 5. Первый запуск

```bash
cd /opt/prototype

# сборка образа (первый раз; дальше образ будет из registry)
docker compose -f docker-compose.prod.yml build app

# запуск: postgres → миграции → приложение/Keycloak/Caddy → первый админ
SKIP_PULL=1 ./deploy/deploy.sh --bootstrap
```

Скрипт:

1. генерирует `keycloak/realm-export.prod.json` с прод-адресами и секретом;
2. поднимает PostgreSQL и применяет `alembic upgrade head`;
3. поднимает остальные сервисы;
4. создаёт администратора в Keycloak (роль `admin`);
5. ждёт `/health`.

Через 30–90 секунд (Keycloak стартует не мгновенно):

- приложение: `https://app.<IP>.sslip.io`
- Keycloak: `https://auth.<IP>.sslip.io` (консоль — `/admin/`)

Первый вход в приложение — `BOOTSTRAP_ADMIN_EMAIL` и его пароль.

## 6. Проверка

```bash
cd /opt/prototype
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f caddy     # сертификат
docker compose -f docker-compose.prod.yml logs -f keycloak
```

- [ ] `https://app.<IP>.sslip.io/health` → `{"status":"ok"}`, сертификат валиден
- [ ] вход через SSO под созданным админом;
- [ ] видны пользователи и журнал аудита;
- [ ] создание/удаление пользователя синхронизируется с Keycloak;
- [ ] выход завершает SSO-сессию;
- [ ] снаружи закрыты 5432/8080 (порты не публикуются вообще).

## 7. Обновление

```bash
cd /opt/prototype
git pull
./deploy/deploy.sh          # pull образа, миграции, перезапуск
```

Если образ собирается на VM:

```bash
BUILD=1 SKIP_PULL=1 ./deploy/deploy.sh
```

## 8. Бэкапы и обслуживание

Managed PostgreSQL нет, поэтому дампы — ваша ответственность. Минимум:

```bash
sudo mkdir -p /opt/backups
sudo tee /opt/backups/backup.sh >/dev/null <<'EOF'
#!/bin/sh
set -e
cd /opt/prototype
ts=$(date +%F_%H%M)
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U app -d app | gzip > /opt/backups/app-$ts.sql.gz
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U keycloak -d keycloak | gzip > /opt/backups/keycloak-$ts.sql.gz
find /opt/backups -name '*.sql.gz' -mtime +14 -delete
EOF
sudo chmod +x /opt/backups/backup.sh

# ежедневно в 3:00
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/backups/backup.sh") | crontab -
```

Дампы стоит складывать в Yandex Object Storage (или забирать на другую
машину): диск VM — не бэкап.

Полезное:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=100 app
docker compose -f docker-compose.prod.yml restart app
```

## 9. Запасной вариант: совсем без DNS и TLS

Если `sslip.io` недоступен, можно поднять HTTP по IP. Это **только для
теста**: пароли и токены идут открытым текстом.

1. В `deploy/Caddyfile` замените два сайта на один с маршрутизацией по путям:

   ```caddyfile
   :80 {
       handle /realms/*    { reverse_proxy keycloak:8080 }
       handle /resources/* { reverse_proxy keycloak:8080 }
       handle /admin/*     { reverse_proxy keycloak:8080 }
       handle /js/*        { reverse_proxy keycloak:8080 }
       handle              { reverse_proxy app:8000 }
   }
   ```

2. В `docker-compose.prod.yml` у `caddy` оставьте только `80:80`.

3. В `.env`:

   ```dotenv
   APP_HOST=<IP>
   AUTH_HOST=<IP>
   APP_URL=http://<IP>
   AUTH_URL=http://<IP>
   ```

4. В `scripts/render-realm-prod.py` принудительно поставьте
   `realm["sslRequired"] = "none"` (или поправьте реалм в консоли Keycloak).

5. Перезапустите `./deploy/deploy.sh`.

## 10. Что дальше

- CI/CD: GitHub Actions собирает образ, пушит в Yandex Container Registry,
  затем `ssh` на VM и `./deploy/deploy.sh` (нужны сервисный аккаунт с ролью
  `container-registry.images.pusher` и секреты в GitHub).
- Секреты — в Yandex Lockbox вместо `.env`.
- Мониторинг — Yandex Monitoring или внешний uptime-check на `/health`.
- При росте нагрузки: вынести PostgreSQL в Managed, а при нескольких
  воркерах приложения — вынести SSO-state в Redis (сейчас `--workers 1`).

## 11. Частые проблемы

| Симптом | Причина | Что делать |
|---|---|---|
| Caddy не выдаёт сертификат | закрыт 80/443 или `sslip.io` не резолвится | проверить security group и `dig app.<IP>.sslip.io`; `docker compose logs caddy` |
| `502` на `auth.*` | Keycloak ещё стартует | подождать 1–2 минуты, смотреть логи keycloak |
| SSO: `redirect_uri` mismatch | `APP_URL` не совпадает с реальным адресом | исправить `.env`, перегенерировать реалм и перезапустить |
| `Invalid username or password` на `auth.*/admin` | это master-реалм, а не приложение | консоль — `KEYCLOAK_ADMIN_USER`; приложение — `BOOTSTRAP_ADMIN_EMAIL` |
| Keycloak не видит БД | init-скрипт выполняется только на пустом томе | проверить `KEYCLOAK_DB_*` до первого старта; иначе создать роль/БД вручную |
| Приложение перезапускается | не хватает RAM | минимум 4 ГБ; проверить `docker stats` |
