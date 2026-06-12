# LaTeX Resume Bullet Char Counter

Count and shorten LaTeX resume bullets to fit reference character limits.

## CLI

```bash
export GEMINI_API_KEY=your-key
python3 tex_char_count.py -r examples/reference.tex -i examples/input.tex -o output.tex
```

## API (Vercel)

### Deploy

1. Install Vercel CLI: `npm i -g vercel`
2. From this directory: `vercel`
3. In [Vercel Dashboard](https://vercel.com) → Project → Settings → Environment Variables:
   - `GEMINI_API_KEY` = your Gemini API key
   - Optional: `GEMINI_MODEL` = `gemini-flash-latest`
   - Optional: `MAX_RL_ATTEMPTS` = `5`

4. Redeploy after adding env vars: `vercel --prod`

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
