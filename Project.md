# Are they still hiring software engineers - The project

We are 12 months since 6 months until [Dario Amadeo predicted 90% of the code will be written by AI](https://www.businessinsider.com/anthropic-ceo-ai-90-percent-code-3-to-6-months-2025-3https://www.businessinsider.com/anthropic-ceo-ai-90-percent-code-3-to-6-months-2025-3). Dario has also bravely re-asserted his prediction in January 2026 saying [we are 6-12 months until AI does all end-to-end software engineering work](https://x.com/slow_developer/status/2013682941201678804).

While this is having a very strong vibes of famous Elon's years of asserting self-driving cars are 1 year away, I believe we should not discard this as a hype! Instead, the only way to understand if we are in this cycle is to see, if the AI hype doctors put the money where their mouth is.

# The Project
Enter are-they-still-hiring-software-engineers.com.

I would like to build an application that will:
- Scrape the job postings on the websites of the top 3 AI companies in the world on the daily basis
- Perist summary of what and how many software-engineering related jobs are posted each day in a postgres database. At minimum the title, location of the role and link to the posting should be persisted for every day
- Provide a humorous UI that:
  - Has the dynamically updating counter of how many months+days we are since Dario said all code will be writted by AI in 6 months (2025-03-14), saying something like `We are x months y days since Dario Amadeo said all code will be written by AI in 6 months`. This should link to the business insider article above.
  - Displays big, green `YES` if any company has software engineering posting as-of a day before. Add confetti and funny sound effect too,
  - Displays scarry, red `NO` if there are no engineering postings as-of a day before. Siren, warning lights etc. are welcome too,
  - Display a chart at the bottom of the page that shows a green bars of total number of postings by date, or scarry warning sign if there were none
  - When clicking individual dates, the user is taken to details page that shows:
    - Summary of total postings on a given day
    - Split down by company
    - Table at the bottom with title, role, location and link to the posting

# Architecture and technical considerations
- Use Python for the backend services and manage packages with `uv`
- Suggest what is the best solution for the front-end
- All build and deployment tooling should be run via `podman`.
- The final artefacts should have a corresponding `systemd` modules that spin up a podman Pod with all the containers necessary for both backend services and the frontend. Those should run it it's own network. More on `podman` systemd integration: https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html
- Scraping of each site should be run as a separate, scheduled processes
- Provide integration tests for all components
- Provide e2e tests for UI
- No bugs!
- Seriously, no bugs or grandma gets it!
