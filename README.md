# LaTeX Resume Bullet Char Counter

Count and shorten LaTeX resume bullets to fit reference character limits.

## CLI

```bash
export GEMINI_API_KEY=your-key
python3 tex_char_count.py -r examples/reference.tex -i examples/input.tex -o output.tex
```

## API (Vercel)

### Deploy (GitHub → Vercel, recommended)

1. Open: [Import tex-char-count on Vercel](https://vercel.com/new/clone?repository-url=https://github.com/yash161/tex-char-count)
2. Add environment variable: `GEMINI_API_KEY` = your Gemini API key
3. Click **Deploy**

**Live API:** `https://counter-kohl-nine.vercel.app`

### Deploy (CLI)

```bash
npx vercel login
npx vercel --prod
npx vercel env add GEMINI_API_KEY   # paste key when prompted
npx vercel --prod                   # redeploy with env var
```

### Test locally

```bash
python3 test_api_local.py
GEMINI_API_KEY=your-key python3 test_api_local.py   # includes /api/shorten
```

### Endpoints

**`GET /api/health`** — health check

**`POST /api/count`** — count chars (no API key needed)

```bash
curl -X POST https://YOUR-PROJECT.vercel.app/api/count \
  -H "Content-Type: application/json" \
  -d '{
    "reference_latex": "\\item \\textbf{...} \\\\ ... % heading CC: orig=94, new=94 | body CC: orig=310, new=310",
    "input_latex": "\\item \\textbf{Your bullet} \\\\ Your body..."
  }'
```

**`POST /api/shorten`** — shorten to fit limits (requires `GEMINI_API_KEY` on server)

```bash
curl -X POST https://YOUR-PROJECT.vercel.app/api/shorten \
  -H "Content-Type: application/json" \
  -d '{
    "reference_latex": "... full reference block with CC comment ...",
    "input_latex": "... full input tabularx block ...",
    "sibling_verbs": ["Optimized", "Deployed", "Redesigned"]
  }'
```

### Response (`/api/shorten`)

```json
{
  "text": "\\begin{tabularx}...full tailored LaTeX...",
  "orig": { "heading": 104, "body": 328 },
  "new": { "heading": 92, "body": 306 },
  "limits": { "heading": 94, "body": 310 },
  "fits": true,
  "method": "gemini-rl",
  "notes": ["Attempt 1: accepted (heading=92, body=306, verb=Designed)."]
}
```
