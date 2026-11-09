# NumberHub — Vercel starter

A no-payment number inventory dashboard with a Flask REST API and MongoDB.

## Safety and authorization
Only add phone numbers you own or are authorized to administer. Only store and distribute OTP records when you have explicit authorization from the number owner and the intended recipient. Do not use this system to intercept verification codes, bypass account security, or access third-party accounts.

## Features
- Admin login using environment credentials
- Add, edit, delete phone-number inventory records
- Country-code field and optional authorized OTP record
- API key generation, one at a time, maximum 10 active keys
- Revoke or delete API keys
- API key plaintext is shown only once; only SHA-256 hashes are stored
- REST endpoints for available number inventory and authorized OTP records

## Deploy to Vercel
1. Create a MongoDB Atlas free-tier cluster and database user. Allow network access from Vercel according to your security requirements.
2. Push this folder to a GitHub repository.
3. Import the repository into Vercel.
4. Add these Environment Variables in Vercel:
   - `MONGODB_URI`
   - `MONGODB_DB` (for example `numberhub`)
   - `ADMIN_USERNAME`
   - `ADMIN_PASSWORD` (use a long unique password)
   - `FLASK_SECRET_KEY` (use a cryptographically random secret)
5. Deploy. Open `/admin` and sign in.

## API
All API endpoints require `X-API-Key`.

### List available numbers
`GET /api/numbers`

### Read an authorized OTP record
`GET /api/numbers/{international_phone}/otp`

### Health
`GET /api/health`

Example:
```bash
curl -H "X-API-Key: YOUR_KEY" https://YOUR-DOMAIN/api/numbers
```

## Important deployment notes
- Vercel Hobby has usage limits and is intended for personal, non-commercial use. Check current Vercel terms before commercial operation.
- Free tiers are not guaranteed lifetime or unlimited. Usage limits, availability, and provider terms can change.
- Use HTTPS only. Keep secrets out of GitHub. Rotate the admin password and API keys if exposed.
- For a production service, add CSRF protection, rate limiting, audit logs, per-customer authorization/ownership checks, and a proper OTP delivery/consent workflow before exposing OTP endpoints publicly.
