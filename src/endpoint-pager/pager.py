"""
ABOUT

This module defines scraper functions (called "pagers" here) for various open data portals (only Socrata thus far).

Ideally, open data portals that we are interested in should provide all of the metadata that we can get about them from
an API endpoint of some kind. Unfortunately, this is often not the case. This module defines web-scraper utilities that
uses Selenium to access this data when it is available on the website interface but is not exposed directly in the API.

Selenium is a web surfing simulator which allows one to programatically access web pages out of a web browser. This is
significantly more complicated to set up and takes longer to run than a bare HTTP request for a page's contents, but
allows us to wait until a page is fully loaded into DOM before scraping it. This is necessary because in many cases
(like in the case of Socrata) most of the page is loaded using AJAX, and the initial payload exposed by an e.g.
requests.get or wget is just going to be a page frame and a big JavaScript glob, not the contents of the page that we
actually want.

Hence we need to open a browser, wait until the page is loaded (using some kind of sentinel for this), and only THEN
run our op. Selenium allows this.

SETUP

You need selenium (pip install selenium) and you need a webdriver. To get the latter, download PhantomJS from their
website (http://phantomjs.org/download.html) and then put the folder containing the executable on your PATH. On Ubuntu
for example this meant running "nano ~/.bashrc", scrolling to the bottom, and appending
":$HOME/$HOME/Desktop/phantomjs-2.1.1-linux-x86_64/bin" to that export list, then closing and reopening the terminal.
To verify that you have added phantomjs to the path correctly, run "echo $HOME" or run "phantomjs -v". Note: do NOT
install phantomjs via apt-get, see further:
http://stackoverflow.com/questions/36770303/phantomjs-with-selenium-unable-to-load-atom-find-element

Further explanations of why this was necessary for certain portals follows:

SOCRATA

The Socrata metadata endpoints includes information on the number of columns, but does not provide any information on
the number of rows, without which it is not possible to know the dimensions of the dataset in question from this source
alone. Socrata portals also disallow HEAD requests and transfer data in a chunk-encoded manner, meaning that there is no
content-length field in their download HTTP headers and therefore no way to know the size of a file ahead of time.

However, their new front page view, which they are calling "Primer", provides both column and row counts. Hence the need
for a Selenium workup for fetching that information.
"""

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException


driver = webdriver.PhantomJS()


# Errors for throwing.
class DeletedEndpointException(Exception):
    pass


def page_socrata(domain, endpoint, timeout=10):
    uri = "https://" + domain + "/d/" + endpoint
    driver.get(uri)
    try:
        # Make sure that the endpoint hasn't been deleted.
        if driver.current_url == "https://" + domain + "/":
            raise DeletedEndpointException
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CLASS_NAME, "dataset-contents"))
        )
        dataset_contents_list = driver.find_elements_by_class_name('dataset-contents')
        assert len(dataset_contents_list) == 1  # check that the UI is what we expect it to be
        metadata_pairs = dataset_contents_list[0].find_elements_by_class_name('metadata-pair')
        # Again we assert that we have the information that we need. However, it's important to note that in some cases,
        # there are *more* than two elements in the "What's in this Dataset?" content block. I'm not at all sure what
        # the rules for this are, but compare one without extras:
        # https://data.cityofnewyork.us/Public-Safety/NYPD-Motor-Vehicle-Collisions/h9gi-nx95
        # With one that has them:
        # https://data.cityofnewyork.us/Housing-Development/Housing-New-York-Units-by-Building/hg8x-zxpr
        # That's ok. We'll include that data but ignore it in the read script itself.
        assert len(metadata_pairs) >= 2
        rowcol = dict()
        for m in metadata_pairs:
            key = m.find_element_by_class_name('metadata-pair-key').text
            value = m.find_element_by_class_name('metadata-pair-value').text
            rowcol.update({key: value})

        # Convert to a machine format. 342K -> 342000, 1M -> 1000000
        rowcol['Columns'] = int(rowcol['Columns'])
        r = rowcol['Rows']
        r = r.replace(",", "")
        if "M" in r:
            r = int(float(r[:-1])  * 1000000)
        elif "K" in r:
            r = int(float(r[:-1])  * 1000)
        else:
            r = int(r)
        rowcol['Rows'] = r

        return rowcol
    except TimeoutException:
        driver.save_screenshot('error.png')
        raise

# Test:
# print(page_socrata("data.cityofnewyork.us", "h9gi-nx95"))