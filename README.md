# ERI Spatiotemporal Environmental Monitoring Website

Static single-page research website designed in the visual spirit of the reference academic project site.

## Run locally

From this folder:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000`.

## GitHub Pages

1. Create a GitHub repository.
2. Upload the contents of this folder to the repository root.
3. Go to **Settings → Pages**.
4. Under **Build and deployment**, choose **Deploy from a branch**.
5. Select the `main` branch and `/ (root)` folder, then save.
6. GitHub will provide the public site URL after deployment.

## Main files

- `index.html` — page content and sections
- `style.css` — academic single-page styling
- `script.js` — GIF selector, filters, and mobile carousel
- `assets/gifs/` — parameter animations
- `assets/docs/` — project PDF, dataset, visualization code
- `assets/images/` — project figures extracted from the project description
