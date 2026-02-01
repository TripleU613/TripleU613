# TripleU Portfolio

A modern, high-performance personal portfolio website with integrated Cloudflare Workers for API caching and data scraping.

## Features

- 🎨 Modern dark theme with blue accents
- ⚡ Lightning-fast loading with Cloudflare Workers
- 🔒 Secure API key management via encrypted environment variables
- 🌍 Global CDN with edge caching
- 📱 Fully responsive design
- 🎭 Smooth animations and transitions
- 🔄 Automated data fetching via cron workers

## Tech Stack

### Frontend
- **HTML5/CSS3** - Semantic markup and modern styling
- **Tailwind CSS** - Utility-first CSS framework
- **JavaScript** - Vanilla JS for interactions
- **Lucide Icons** - Beautiful icon set
- **Font Awesome** - Additional icons

### Backend & Infrastructure
- **Cloudflare Pages** - Hosting and deployment
- **Cloudflare Workers** - Serverless API handlers
- **Cloudflare KV** - Global key-value storage
- **Cloudflare Browser Rendering** - Headless browser for scraping

## Architecture

### API Caching Worker
Location: `workers/api-cache.js`

Handles all external API calls with intelligent caching:
- **JTech Forums** - Latest forum posts (15min cache)
- **GitHub Activity** - Recent contributions (10min cache)
- **Mitmachim** - Community activity (1hr cache)

### Scraper Cron Worker
Location: `workers/scraper-cron.js`

Automated web scraping via Cloudflare cron triggers:
- Runs every 5 hours
- Uses Puppeteer for browser automation
- Stores data in Cloudflare KV
- Zero GitHub Actions required

## Setup

### Prerequisites
- Node.js 18+
- Cloudflare account
- Wrangler CLI: `npm install -g wrangler`

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/TripleU613/tripleu.git
   cd tripleu
   ```

2. **Install dependencies**
   ```bash
   npm install
   cd workers && npm install
   ```

3. **Start dev server**
   ```bash
   npm run dev
   ```
   Visit http://localhost:8000

### Deploy Workers

1. **Login to Cloudflare**
   ```bash
   wrangler login
   ```

2. **Create KV namespace**
   ```bash
   wrangler kv:namespace create "API_CACHE"
   ```
   Update the namespace ID in `workers/wrangler.toml` and `workers/wrangler-scraper.toml`

3. **Set secrets**
   ```bash
   wrangler secret put JTECH_API_KEY
   wrangler secret put GITHUB_TOKEN
   ```

4. **Update configuration**
   - Edit `workers/wrangler.toml` and `workers/wrangler-scraper.toml`
   - Replace `YOUR_CLOUDFLARE_ACCOUNT_ID` with your account ID
   - Replace `YOUR_KV_NAMESPACE_ID` with the ID from step 2

5. **Deploy workers**
   ```bash
   cd workers
   npm run deploy-all
   ```

6. **Update frontend**
   - Edit `index.html`
   - Replace worker URLs with your deployed worker URLs

7. **Deploy to Cloudflare Pages**
   - Push to GitHub
   - Connect repository in Cloudflare Pages dashboard
   - Set build command: (none - static site)
   - Set build output directory: `/`

## Configuration

### Environment Variables (Cloudflare Secrets)
- `JTECH_API_KEY` - JTech Forums API key
- `GITHUB_TOKEN` - GitHub Personal Access Token

### Cloudflare Pages Settings
The `_headers` file configures:
- Security headers (CSP, HSTS, etc.)
- Cache control for static assets
- CORS policies

## Project Structure

```
tripleu/
├── assets/
│   ├── images/          # Profile images and banners
│   └── videos/          # Profile videos
├── workers/
│   ├── api-cache.js     # Main API caching worker
│   ├── scraper-cron.js  # Scheduled scraper worker
│   ├── wrangler.toml    # API worker config
│   └── wrangler-scraper.toml  # Scraper config
├── .github/
│   └── dependabot.yml   # Dependency updates
├── .well-known/
│   └── security.txt     # Security policy
├── index.html           # Main page
├── _headers             # Cloudflare Pages headers
├── robots.txt           # SEO configuration
├── sitemap.xml          # Sitemap
├── humans.txt           # Credits
└── package.json         # Dependencies
```

## Performance

- **First Load**: ~200ms with loading animation
- **Cached Loads**: <50ms (served from KV)
- **Global CDN**: <10ms latency worldwide
- **Lighthouse Score**: 95+ across all metrics

## Security

- ✅ Content Security Policy (CSP)
- ✅ Strict Transport Security (HSTS)
- ✅ XSS Protection
- ✅ No exposed API keys
- ✅ Encrypted secrets in Cloudflare
- ✅ Regular dependency updates via Dependabot

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

ISC License - See package.json for details

## Credits

Built with ❤️ by TripleU

Special thanks to:
- Cloudflare for amazing Workers platform
- Tailwind CSS for the utility framework
- The open source community

## Links

- **Website**: [tripleu.org](https://tripleu.org)
- **JTech Forums**: [jtechforums.org](https://jtechforums.org)
- **TripleU MDM**: [tripleumdm.com](https://tripleumdm.com)
- **GitHub**: [@TripleU613](https://github.com/TripleU613)
