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

<!-- ROADMAP -->
## Roadmap

- [X] Scheduled Updates
- [ ] Improved Logging
- [ ] Retireve ...
    - [ ] DNS Record(s) Information
    - [ ] IP2ASN Information
    - [ ] WHOIS Information
    - [ ] Reverse WHOIS (by Name) Information
    - [ ] Certficates
    - [ ] VirusTotal Information

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
