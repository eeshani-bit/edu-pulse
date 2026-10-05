# Edu Pulse

A self-updating higher-education news page (India first, global too), sorted by topic.
GitHub fetches fresh news every 3 hours and republishes the site. No server, no cost.

## Files
- `index.html`: the website
- `fetch_news.py`: collects news and tags topics
- `config.json`: your sources and topic keywords (the file you will edit most)
- `news.json`: the data the site reads (rewritten automatically)
- `.github/workflows/update.yml`: the schedule that runs everything

## Customising
- **Add or remove a source:** edit the `sources` list in `config.json`. Any RSS link works.
  Google News links (`news.google.com/rss/search?q=...`) let you follow any search term.
- **Change topics:** edit `categories` in `config.json`. Each topic is a list of keywords.
- **Change update frequency:** edit the `cron` line in `update.yml` (`*/3` means every 3 hours).

## If something looks wrong
- Open the Actions tab, click the latest run, open "Fetch and categorise news".
  It lists every source with the number of stories fetched or the reason it failed.
- GitHub pauses scheduled runs after 60 days with no repository activity.
  If updates stop, open the Actions tab and click "Enable workflow", or run it once by hand.
