<a name="readme-top"></a>
[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]



<!-- PROJECT LOGO -->
<br />
<div align="center">
  <a href="https://github.com/StrackVibes/NRD-db">
    <img src="https://i.ibb.co/bHVd4rQ/NRD-db1.png" alt="Logo">
  </a>

<h3 align="center">NRD-db</h3>

  <p align="center">
  Welcome to the NRD-db (Newly Registered Domains with Redis) GitHub repository! NRD-db is a Docker image designed to automatically fetch and store newly registered domains in a Redis database. It simplifies the process of populating a Redis database with up-to-date domain information, making it a great fit for use with Arkime's WISE tagging.
    <br />
    <br />
    ·
    <a href="https://github.com/StrackVibes/NRD-db/issues">Report Bug</a>
    ·
    <a href="https://github.com/StrackVibes/NRD-db/issues">Request Feature</a>
  </p>
</div>



<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#variables">Variables</a></li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#enrichment">Enrichment</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>



<!-- ABOUT THE PROJECT -->
## About The Project
The primary objective of NRD-db is to provide an automated solution for keeping your Redis database up-to-date with newly registered domains. Searching through local text files for specific domains can be inefficient, and that's where NRD-db comes in. It fetches domain data from the WhoisDS service and stores it in a Redis database, allowing you to access this information efficiently.
[![Product Name Screen Shot][product-screenshot]](https://example.com)

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- GETTING STARTED -->
## Getting Started

To get a local copy up and running follow these simple example steps. 

### Prerequisites

Before you begin, ensure that you have the following dependencies installed:
* Docker
  ```sh
  sudo apt install docker-ce -g
  ```
  NOTE: To avoid using sudo for docker activities, add your username to the Docker Group
  ```sh
  sudo usermod -aG docker ${USER}
  ```

### Installation
You can build and run the NRD-db Docker container using the following commands:
1. Clone the repo
   ```sh
   git clone https://github.com/StrackVibes/NRD-db.git
   ```
2. Build the Docker image
   ```sh
   cd NRD-db
   docker build -t nrd-db .
   ```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Variables

You can customize the NRD fetching and storage process by setting environment variables with the docker '**--env**' argument or permanently in the NRD.sh script. Here are the available variables:

| NAME                     | DEFAULT VALUE   | NOTES                                                                    |
| --------------           | --------------- | -----------------------------------------------------------------------  |
| DIR                      | /opt/nrd        | The directory where NRD-db stores files and data.                        |
| DAY_RANGE                | 1               | The number of days you want to fetch newly registered domains for.       |
| DAILY_DIR                | /tmp/daily      | The directory where NRD-db stores temporary daily domain data files.     |
| TEMP_FILE                | /tmp/nrd        | The path to the temporary file used during domain data retrieval.        |
| PAID_WHOISDS_USERNAME    |                 | Your WhoisDS username for accessing paid data (if applicable)            |
| PAID_WHOISDS_PASSWORD    |                 | Your WhoisDS password for accessing paid data (if applicable)            |
| BASE_URL_FREE | [Free](https://whoisds.com/whois-database/newly-registered-domains) | The base URL for fetching newly registered domain data for free. |
| BASE_URL_PAID | [Paid](https://whoisds.com/your-download/direct-download_file/USERNAME/PASSWORD) | The base URL for fetching newly registered domain data with your WhoisDS paid credentials.|

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- USAGE EXAMPLES -->
## Usage

### **Note**: By default, The docker container will pull the NRDs at 0800 UTC according to the cronjob.

After configuring the environment variables, simply run the NRD-db Docker container, and it will start fetching newly registered domains based on the default variables in nrd.sh.
   ```sh
   docker run -d nrd-db
   ```
By default, NRD-db is set to fetch NRD data for the last 1 day. You can adjust the **DAY_RANGE** variable to specify a different day range.
   ```sh
   docker run -d nrd-db --env DAY_RANGE=10
   ```
You can use the **PAID_WHOISDS_USERNAME** and **PAID_WHOISDS_PASSWORD** variables if you have a paid WhoisDS subscription. If not, the tool will use the free data source by default.
   ```sh
   docker run -d nrd-db --env PAID_WHOISDS_USERNAME=ThreatHunter --env PAID_WHOISDS_PASSWORD=NeRD
   ```
With this **docker-compose.yml** example, you can easily launch the NRD-db service with following:
  ```sh
version: '3'

services:
  nrd:
    image: nrd
    build: ./Dockerfile
    container_name: nrd
    restart: always
    ports:
      - "6379:6379"
    volumes:
      - ./nrd/:/root/redis
      - ./nrd/redis.conf:/usr/local/etc/redis/redis.conf
      - ./nrd/collection/:/opt/nrd/
    environment:
      - REDIS_PASSWORD=my-password
      - REDIS_PORT=6379
      - REDIS_DATABASES=1
  ```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ENRICHMENT -->
## Enrichment

The `enrich/` directory is a separate sidecar container (`nrd-enrich`, built from `enrich/Dockerfile`) that enriches each day's newly-added domains with DNS, IP2ASN, WHOIS, Certificate Transparency, and VirusTotal data. It's kept out of the main `nrd` image on purpose: that image has no Python, and the Redis instance it runs has no auth (by default `redis.conf` isn't actually wired up, so Redis falls back to defaults — set `requirepass` if you expose port 6379 beyond a trusted network). Keeping all the new outbound-networking code in its own container limits the blast radius if any of it misbehaves.

**This never touches the existing `<domain> -> registration date` keys.** Everything the enrichment pipeline writes lives under a separate `nrd:enrich:` prefix, so anything already reading the flat keys (e.g. Arkime WISE) is unaffected. To pull enrichment data into WISE, add a second WISE source pointing at the `nrd:enrich:<domain>` hash.

### Redis schema

`nrd:enrich:<domain>` — a Hash per domain (TTL 180 days, independent of the flat keys which never expire):

| Field | Meaning |
|---|---|
| `dns_status`, `dns_a`, `dns_aaaa`, `dns_ns`, `dns_mx`, `dns_checked_at` | DNS resolution against public resolvers, not the host's own DNS |
| `asn_status`, `asn_info` (JSON), `asn_checked_at` | IP2ASN via Team Cymru's bulk whois service, for domains that resolved |
| `whois_status`, `whois_registrar`, `whois_created_date`, `whois_expires_date`, `whois_source`, `whois_attempts`, `whois_checked_at` | RDAP first, legacy port-43 WHOIS fallback |
| `reverse_whois_status` | Always `no_provider_configured` — **no free/self-hosted reverse-WHOIS-by-name source exists.** This is a labeled stub with a config slot (`REVERSE_WHOIS_PROVIDER`/`REVERSE_WHOIS_API_KEY`) for a future paid provider (WhoisXML, SecurityTrails, DomainTools, etc.), not a working implementation. |
| `crt_status`, `crt_cert_count`, `crt_first_seen_not_before`, `crt_latest_issuer`, `crt_checked_at` | Certificate Transparency via crt.sh's public Postgres mirror |
| `vt_status`, `vt_malicious`, `vt_suspicious`, `vt_harmless`, `vt_checked_at` | VirusTotal — only runs at all if `VT_API_KEY` is set |

`nrd:enrich:runs:<date>:<source>` — per-run counters (Hash, TTL 30 days) for observability without scanning every domain hash.

### Honest coverage caveats

This pipeline processes ~70,000 domains/day. DNS and IP2ASN are free, bulk-safe, and cover the full daily cohort. **WHOIS and VirusTotal do not** — full same-day coverage isn't realistic (or safe) against free/rate-limited registries and VirusTotal's public API tier:

- **WHOIS** works a rolling lookback window (`WHOIS_LOOKBACK_DAYS`, default 3 days) with a per-registry-host rate limit and circuit breaker, so most registries only ever see a couple of requests a second at most. Many domains will simply stay `whois_status=not_attempted` or `unsupported_tld` — that's expected, not a bug.
- **VirusTotal** is fully optional (`VT_API_KEY` unset ⇒ zero requests, every domain marked `vt_status=no_api_key`) and, even with a key, defaults to VT's public free-tier limits (4 req/min, 500/day) — nowhere near enough to cover 70k domains/day. It prioritizes domains that actually resolved over ones that don't, and the rest are left `not_attempted`.
- **Reverse WHOIS by name** has no free source at all; see the schema table above.

### Configuration

All tunables are env vars read by `enrich/config.py`, set via the `nrd-enrich` service's `environment:` block in the outer `docker-compose.yml` (or a gitignored `enrich/.env`, see `enrich/.env.example`). Notable ones: `VT_API_KEY`, `VT_REQ_PER_MIN`, `VT_REQ_PER_DAY`, `WHOIS_LOOKBACK_DAYS`, `WHOIS_GLOBAL_CONCURRENCY`, `DNS_CONCURRENCY`, `ENRICH_TTL_DAYS`. See `enrich/config.py` for the full list and defaults.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ROADMAP -->
## Roadmap

- [X] Scheduled Updates
- [ ] Improved Logging
- [X] Retrieve ...
    - [X] DNS Record(s) Information
    - [X] IP2ASN Information
    - [X] WHOIS Information
    - [ ] Reverse WHOIS (by Name) Information — no free/self-hosted source exists; stub only, needs a paid provider (see [Enrichment](#enrichment))
    - [X] Certificates
    - [X] VirusTotal Information — optional, gated on `VT_API_KEY`; free-tier coverage is necessarily partial

See the [open issues](https://github.com/StrackVibes/NRD-db/issues) for a full list of proposed features (and known issues).

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- CONTRIBUTING -->
## Contributing

Contributions are what makes the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

If you have a suggestion that would make this better, please fork the repo and create a pull request. You can also simply open an issue with the tag "enhancement".
Don't forget to give the project a star! Thanks again!

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- LICENSE -->
## License

Distributed under the Chicken Dance License. See `LICENSE.md` for more information.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- CONTACT -->
## Contact

Shane Strack - [@inshane09](https://twitter.com/inshane09)

Project Link: [https://github.com/StrackVibes/NRD-db](https://github.com/StrackVibes/NRD-db)

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- ACKNOWLEDGMENTS -->
## Acknowledgments

* [PeterDaveHello](https://github.com/PeterDaveHello/nrd-list-downloader)
* [WhoisDS.com](https://www.whoisds.com/newly-registered-domains)

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->
[contributors-shield]: https://img.shields.io/github/contributors/StrackVibes/NRD-db.svg?style=for-the-badge
[contributors-url]: https://github.com/StrackVibes/NRD-db/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/StrackVibes/NRD-db.svg?style=for-the-badge
[forks-url]: https://github.com/StrackVibes/NRD-db/network/members
[stars-shield]: https://img.shields.io/github/stars/StrackVibes/NRD-db.svg?style=for-the-badge
[stars-url]: https://github.com/StrackVibes/NRD-db/stargazers
[issues-shield]: https://img.shields.io/github/issues/StrackVibes/NRD-db.svg?style=for-the-badge
[issues-url]: https://github.com/StrackVibes/NRD-db/issues
[license-shield]: https://img.shields.io/github/license/StrackVibes/NRD-db.svg?style=for-the-badge
[license-url]: https://github.com/StrackVibes/NRD-db/blob/master/LICENSE.md
[product-screenshot]: images/screenshot.png
