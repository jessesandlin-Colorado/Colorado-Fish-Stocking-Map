# Publish with GitHub Pages

## 1. Create the repository

1. Sign in to GitHub.
2. Create a new public repository, for example `colorado-fish-stocking-map`.
3. Do not add a README, license, or `.gitignore` on GitHub; this folder already contains them.

## 2. Upload this project with Git

Open Command Prompt in this project folder and run:

```cmd
git init
git add .
git commit -m "Initial Colorado fish stocking map"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/colorado-fish-stocking-map.git
git push -u origin main
```

Replace `YOUR-USERNAME` with your GitHub username.

## 3. Enable GitHub Pages

1. Open the repository on GitHub.
2. Select **Settings**.
3. Select **Pages**.
4. Under **Build and deployment**, choose **GitHub Actions**.
5. Open the **Actions** tab and watch the `Deploy site` workflow.

The published address will normally be:

`https://YOUR-USERNAME.github.io/colorado-fish-stocking-map/`

## 4. Refresh data manually

Open **Actions** → **Refresh CPW data** → **Run workflow**.

The workflow is also scheduled for Saturday morning in Colorado during daylight-saving time. GitHub schedules use UTC and can run later than the exact scheduled minute.

## 5. Custom domain later

A custom domain can be connected in **Settings** → **Pages** after the site is live.
