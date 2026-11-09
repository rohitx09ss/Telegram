# NumberHub — Vercel + MongoDB

## Vercel environment variables
Set `MONGODB_URI`, `MONGODB_DB`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `FLASK_SECRET_KEY`.
Use a MongoDB database user with only the permissions this app needs. Never commit `.env`.

## CSV format
CSV header: `country_code,phone`
Example:
```csv
country_code,phone
+91,8928066524
+91,9876543210
```
This import deliberately ignores OTP/password columns. It is for authorized number inventory only.

## API
Send header `X-API-Key: YOUR_KEY`.
- `GET /api/health`
- `GET /api/numbers/available`
- `POST /api/numbers/reserve` JSON `{"number_id":"..."}`
- `GET /api/orders/ORDER_ID`

## Deploy
Import this repository into Vercel. Framework: Other; Root Directory: `./`; leave build/output overrides blank. Add environment variables and deploy.

## Important security notes
This is a minimal starter, not a production-hardened commercial service. Before real customer use add rate limits, CSRF protection for admin actions, audit logs, customer/order ownership binding, reservation expiry, and monitoring. Do not distribute preloaded OTPs or passwords to arbitrary API customers. Verification codes should only be generated for a user-initiated flow by a service you control and delivered to the authorized recipient. Keep customer data and phone numbers only with appropriate consent and legal basis.


## Admin inventory updates
- Select multiple active numbers and export them as CSV (phone numbers only; no OTP values).
- Deleting an active number archives its number, status, timestamp, and reason in `deleted_numbers`, then removes it from active inventory.
- Deleted History is visible in the admin panel.

This starter does not store, export, or distribute preloaded OTPs. OTP handling should be implemented only for a user-initiated verification challenge, with results restricted to that same authorized user.
