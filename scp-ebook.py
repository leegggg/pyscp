#!/usr/bin/env python3

from bs4 import BeautifulSoup as bs4
from lxml import etree, html
import re
import os
import shutil
import copy
import time
import requests
import tempfile


class Page():

    """placeholder docstring"""

    #titles for scp articles
    image_whitelist = {"http://scp-wiki.wdfiles.com/local--files/scp-406/10665"
                       "29_0ca423c3.jpg": "http://www.geograph.org.uk/profile/22761"}
    scp_index = {}

    def __init__(self, url=None):
        self.url = url
        self.tags = []
        self.author = None
        self.title = None
        if url is not None:
            self.scrape()
            self.cook()
        self.override()

    def override(self):
        if self.url == "http://www.scp-wiki.net/scp-1047-j": self.data = None
        elif self.url == "http://www.scp-wiki.net/scp-2998":
            self.list_children = lambda: [Page(i.url + "-" + str(n))
                                          for n in range(2,11)]
        elif self.title == "Wills And Ways":
            x = [k for k in self.list_children() if k.title !=
                 "Marshall, Carter and Dark Hub "]
            self.list_children = lambda: x
        elif self.title == "Serpent's Hand Hub":
            x = [k for k in self.list_children() if k.title !=
                 "Black Queen Hub"]
            self.list_children = lambda: x
        elif self.url == "Chicago Spirit Hub":
            self.list_children = lambda: []

    def scrape(self):
        '''Scrape the contents of the given url.'''
        def cached(path, scrape_func):
            if os.path.isfile(path):
                with open(path, "r") as F:
                    return F.read()
            else:
                data = scrape_func()
                if data is not None:
                    with open(path, "w") as F:
                        F.write(data)
                return data
        def scrape_page_body():
            print("downloading: \t" + self.url)
            try:
                soup = bs4(requests.get(self.url).text)
            except Exception as e:
                print("ERROR: " + str(e))
                return None
            return str(soup)
        def scrape_history():
            if self.soup is None:
                return None
            print("d-ing history: \t" + self.url)
            pageid = re.search("pageId = ([^;]*);", self.soup)
            if pageid is not None:
                pageid = pageid.group(1)
            else:
                return None
            headers = {"Content-Type": "application/x-www-form-urlencoded;",
                       "Cookie": "wikidot_token7=123456;"}
            payload = ("page=1&perpage=1000&page_id=" + pageid +
                       "&moduleName=history%2FPageRevisionListModule"
                       "&wikidot_token7=123456")
            try:
                data = requests.post("http://www.scp-wiki.net/ajax-module-"
                                     "connector.php", data=payload,
                                     headers=headers).json()["body"]
            except Exception as e:
                print("ERROR: " + str(e))
                return None
            return data
        cfile = re.search("/[^/]*$", self.url).group()[1:]
        if cfile == "": 
            self.soup = None
            return
        self.soup = cached("data/" + cfile, scrape_page_body)
        self.history = cached("data/history/" + cfile, scrape_history)

    def cook(self):
        '''Cook the soup, retrieve title, data, and tags'''
        if not self.soup:
            self.title = None
            self.data = None
            return
        soup = bs4(self.soup)
        # meta
        self.tags = [a.string for a in soup.select("div.page-tags a")]
        if self.history is not None:
            self.author = bs4(self.history)\
                          .select("tr")[-1].select("td")[-3].text
        # title
        if soup.select("#page-title"):
            title = soup.select("#page-title")[0].text.strip()
        else:
            title = ""
        # because 001 proposals don't have their own tag,
        # it's easier to check if the page is a mainlist skip
        # by regexping its url instead of looking at tags
        if "scp" in self.tags and re.match(".*scp-[0-9]{3,4}$", self.url):
            if Page.scp_index == {}:
                index_urls = ["http://www.scp-wiki.net/scp-series",
                              "http://www.scp-wiki.net/scp-series-2",
                              "http://www.scp-wiki.net/scp-series-3"]
                for u in index_urls:
                    s = bs4(Page(u).soup)
                    entries = s.select("ul li")
                    for e in entries:
                        if re.match(".*>SCP-[0-9]*<.*", str(e)):
                            i = e.text.split(" - ")
                            Page.scp_index[i[0]] = i[1]
            title = title + ": " + Page.scp_index["SCP-" + title[4:]]
        self.title = title
        # body
        if not soup.select("#page-content"):
            self.data = None
            return
        data = soup.select("#page-content")[0]
        garbage = ["div.page-rate-widget-box", "div.scp-image-block"]
        [k.decompose() for e in garbage for k in data.select(e)]
        for i in data.select("img"):
            if i["src"] not in Page.image_whitelist:
                for k in i.parents:
                    if k.name == "table": k.decompose(); break
                    if "class" in k and k["class"] == "scp-image-block":
                            k.decompose()
                            break
                i.decompose()
            else:
                i["src"] = "images/" + "_".join([i["src"].split("/")[-2],
                                                i["src"].split("/")[-1]])
        # tables
        # tab-views
        for i in data.select("div.yui-navset"):
            wraper = soup.new_tag("div", **{"class": "tabview"})
            titles = [a.text for a in i.select("ul.yui-nav em")]
            tabs = i.select("div.yui-content > div")
            for k in tabs:
                k.attrs = {"class": "tabview-tab"}
                tab_title = soup.new_tag("div", **{"class": "tab-title"})
                tab_title.string = titles[tabs.index(k)]
                k.insert(0, tab_title)
                wraper.append(k)
            i.replace_with(wraper)
        # footnotes
        for i in data.select("sup.footnoteref"):
            i.string = i.a.string
        for i in data.select("div.footnote-footer"):
            i["class"] = "footnote"
            del(i["id"])
            i.string = "".join([k for k in i.strings])
        # collapsibles
        for i in data.select("div.collapsible-block"):
            link_text = i.select("a.collapsible-block-link")[0].text
            content = i.select("div.collapsible-block-content")[0]
            if content.text == "":
                content =  i.select("div.collapsible-block-unfolded")[0]
                del(content["style"])
                content.select("div.collapsible-block-content")[0].decompose()
                content.select("div.collapsible-block-unfolded-link"
                               )[0].decompose()
            content["class"] = "collaps-content"
            col = soup.new_tag("div", **{"class": "collapsible"})
            content = content.wrap(col)
            col_title = soup.new_tag("div", **{"class": "collaps-title"})
            col_title.string = link_text
            content.div.insert_before(col_title)
            i.replace_with(content)
        # links
        for i in data.select("a"):
            del(i["href"])
            i.name = "span"
            i["class"] = "link"
        #quote boxes
        for i in data.select("blockquote"):
            i.name = "div"
            i["class"] = "quote"
        #add title to the page
        if "scp" in self.tags:
            data = "<p class='scp-title'>" + self.title + "</p>" + str(data)
        else:
            data = "<p class='tale-title'>" + self.title + "</p>" + str(data)
        self.data = data


    def list_children(self):
        def links(self):
            links = []
            soup = bs4(self.soup)
            for a in soup.select("#page-content a"):
                if not a.has_attr("href") or a["href"][0] != "/": continue
                    # this whole section up to 'continue' is for
                    # debug purposes only, can be deleted in the final version
                    # if a.has_attr("href"):
                    #     if (a["href"] != "javascript:;" and a["href"][0] != "#"
                    #         and re.search("scp-wiki", a["href"])
                    #             and not re.search("local--files", a["href"])):
                    #         print("bad link on page " + self.url + "\t(" +
                    #               a["href"] + ")")
                    # continue
                if a["href"][-4:] in [".png", ".jpg", ".gif"]: continue
                url = "http://www.scp-wiki.net" + a["href"]
                url = url.rstrip("|")
                if url in links: continue
                links.append(url)
            return links
        if not any(i in self.tags for i in ["scp", "hub", "splash"]):
            return []
        lpages = []
        for url in links(self):
            p = Page(url)
            if p.soup and p.data:
                lpages.append(p)
        if any(i in self.tags for i in ["scp", "splash"]):
            mpages = [i for i in lpages if
                      any(k in i.tags for k in ["supplement", "splash"])]
            return mpages
        if "hub" in self.tags and any(i in self.tags
                                      for i in ["tale", "goi2014"]):
            mpages = [i for i in lpages if any(k in i.tags for k in
                      ["tale", "goi-format", "goi2014"])]

            def backlinks(page, child):
                if page.url in links(child):
                    return True
                soup = bs4(child.soup)
                if soup.select("#breadcrumbs a"):
                    crumb = soup.select("#breadcrumbs a")[-1]
                    crumb = "http://www.scp-wiki.net" + crumb["href"]
                    if self.url == crumb:
                        return True
                return False
            if any(backlinks(self, p) for p in mpages):
                return [p for p in mpages if backlinks(self, p)]
            else:
                return mpages


class Epub():

    """"""

    allpages_global = []

    def __init__(self, title):
        self.title = title
        #change to a proper temp dir later on
        self.dir = tempfile.TemporaryDirectory()
        self.templates = {}
        for i in os.listdir("templates"):
            self.templates[i.split(".")[0]] = etree.parse(os.getcwd() +
                                                          "/templates/" + i)
        self.allpages = []
        #pre-building toc
        toc = self.templates["toc"]
        for i in toc.getroot().iter():
            if i.tag.endswith("text"):
                i.text = title
        self.toc = toc
        self.images = []

    def add_page(self, page, node=None):
        if page.url in Epub.allpages_global:
            return
        #print(page.title)
        n = len(self.allpages)
        uid = "page_" + str(n).zfill(4)
        epub_page = copy.deepcopy(self.templates["page"])
        for i in epub_page.getroot().iter():
            if i.tag.endswith("title"):
                i.text = page.title
            elif i.tag.endswith("body"):
                body = html.fromstring(page.data)
                i.append(body)
        epub_page.write(self.dir.name + "/" + uid + ".xhtml")
        for i in bs4(page.soup if hasattr(page, "soup") else "").select("img"):
            if i["src"] in Page.image_whitelist:
                self.images.append(i["src"])
        self.allpages.append({"title": page.title, "id": uid,
                              "author": page.author, "url": page.url})
        if page.url is not None: Epub.allpages_global.append(page.url)

        def add_to_toc(node, page, uid):
            if node is None:
                node = self.toc.getroot().find("{http://www.daisy.org/z3986/"
                                               "2005/ncx/}navMap")
            navpoint = etree.SubElement(node, "navPoint", id=uid,
                                        playOrder=str(len(self.allpages)))
            navlabel = etree.SubElement(navpoint, "navLabel")
            etree.SubElement(navlabel, "text").text = page.title
            etree.SubElement(navpoint, "content", src=uid + ".xhtml")
            return navpoint
        new_node = add_to_toc(node, page, uid)
        [self.add_page(i, new_node) for i in page.list_children()]

    def save(self, filename):
        self.toc.write(self.dir.name + "/toc.ncx", xml_declaration=True,
                       encoding="utf-8", pretty_print=True)
        #building the spine
        spine = self.templates["content"]
        self.allpages.sort(key=lambda k: k["id"])
        for i in spine.getroot().iter():
            if i.tag.endswith("meta"):
                if ("property" in i.attrib and
                        i.attrib["property"] == "dcterms:modified"):
                    i.text = time.strftime("%Y-%m-%dT%H:%M:%SZ")
            elif i.tag.endswith("title"):
                i.text = self.title
            elif i.tag.endswith("manifest"):
                for k in self.allpages:
                    etree.SubElement(i, "item",
                                     href=k["id"] + ".xhtml", id=k["title"],
                                     **{"media-type":
                                        "application/xhtml+xml"})
            elif i.tag.endswith("spine"):
                for k in self.allpages:
                    etree.SubElement(i, "itemref", idref=k["title"])
        os.mkdir(self.dir.name + "/images/")
        if not os.path.exists("data/images/"): os.mkdir("data/images/")
        for i in self.images:
            path = "_".join([i.split("/")[-2], i.split("/")[-1]])
            if not os.path.isfile("data/images/" + path):
                with open("data/images/" + path, "wb") as F:
                    shutil.copyfileobj(requests.get(i, stream=True).raw, F)
            shutil.copy("data/images/" + path, self.dir.name + "/images/")
        spine.write(self.dir.name + "/content.opf", xml_declaration=True,
                    encoding="utf-8", pretty_print=True)
        #other necessary files
        container = self.templates["container"]
        os.mkdir(self.dir.name + "/META-INF/")
        container.write(self.dir.name + "/META-INF/container.xml",
                        xml_declaration=True, encoding="utf-8",
                        pretty_print=True)
        with open(self.dir.name + "/mimetype", "w") as F:
            F.write("application/epub+zip")
        shutil.copy("stylesheet.css", self.dir.name)
        shutil.copy("cover.png", self.dir.name)
        shutil.make_archive(filename, "zip", self.dir.name)
        shutil.move(filename + ".zip", filename + ".epub")


def yield_pages():
    def urls_by_tag(tag):
        soup = bs4(requests.get("http://www.scp-wiki.net/system:"
                             "page-tags/tag/" + tag).text)
        urls = ["http://www.scp-wiki.net" + a["href"] for a in
                soup.select("""div.pages-list
                            div.pages-list-item div.title a""")]
        return urls
    def natural_key(s):
        re_natural = re.compile('[0-9]+|[^0-9]+')
        return [(1, int(c)) if c.isdigit() else (0, c.lower()) for c
                in re_natural.findall(s)] + [s]
    # skips
    scp_main = [i for i in urls_by_tag("scp") if re.match(".*scp-[0-9]*$", i)]
    scp_main = sorted(scp_main, key=natural_key)
    scp_blocks = [[i for i in scp_main if (int(i.split("-")[-1]) // 100 == n)]
                  for n in range(30)]
    for b in scp_blocks[4:5]:
        b_name = "SCP Database/Chapter " + str(scp_blocks.index(b) + 1)
        for url in b:
            p = Page(url)
            p.chapter = b_name
            yield p
    return
    
    def quick_yield(tags, chapter_name):
        L = [urls_by_tag(i) for i in tags if type(i) == str]
        for i in [i for i in tags if type(i) == list]:
            a = [x for k in i for x in urls_by_tag(k)]
            L.append(a)
        for url in [i for i in L[0] if all(i in t for t in L)]:
            p = Page(url)
            p.chapter = chapter_name
            yield p
    #yield from quick_yield(["joke", "scp"], "SCP Database/Joke Articles")
    #yield from quick_yield(["explained", "scp"],
    #                      "SCP Database/Explained Phenomena")
    hubhubs = ["http://www.scp-wiki.net/canon-hub",
               "http://www.scp-wiki.net/goi-contest-2014",
               "http://www.scp-wiki.net/acidverse"]
    nested_hubs = [i.url for k in hubhubs for i in Page(k).list_children()]
    for i in quick_yield(["hub", ["tale", "goi2014"]], "Canons and Series"):
        if i.url not in nested_hubs:
            yield i
    #yield from quick_yield(["tale"], "Assorted Tales")


def main():
    def add_static_pages(book):
        static_pages =[ ]
        for xf in [i for i in sorted(os.listdir(os.getcwd() + "/pages"))]:
            p = Page()
            p.title = xf[3:-6]
            with open(os.path.join(os.getcwd() + "/pages", xf)) as F:
                p.data = F.read()
            static_pages.append(p)
        [book.add_page(p) for p in static_pages]
    def add_attributions(book, overrides):
        attrib = Page()
        attrib.title = "Acknowledgments and Attributions"
        attrib.data = "<div class='attrib'>"
        for i in sorted(book.allpages, key=lambda k: k["id"]):
            def add_one(attrib, title, url, author, r=None):
                attrib.data += "<p><b>" + title + "</b> (" + url +\
                               ") was written by <b>" + author + "</b>"
                if r is not None:
                    attrib.data += " and rewritten by <b>" + r + "</b>.</p>"
                else:
                    attrib.data += ".</p>"
            if i["url"] is None:
                continue
            tail = i["url"].split("/")[-1]
            if tail in overrides:
                if overrides[tail][:10] == ":override:":
                    add_one(attrib, i["title"], i["url"], overrides[tail][10:])
                else:
                    add_one(attrib, i["title"], i["url"], i["author"],
                            overrides[tail])
            elif i["author"] not in [None, "(account deleted)"]:
                add_one(attrib, i["title"], i["url"], i["author"])
        attrib.data += "</div>"
        book.add_page(attrib)
    def goes_in_book(previous_book, page):
        def increment_title(old_title):
            n = old_title[-2:]
            n = str(int(n) + 1).zfill(2)
            return old_title[:-2] + n
        if ("scp" in page.tags and
            page.chapter.split("/")[-1] in previous_book.chapters):
                return previous_book.title
        elif (page.chapter == "Canons and Series" and
              previous_book.title[-4:-3] == "1"):
                return "SCP Foundation: Tome 2.01"
        elif (page.chapter == "Assorted Tales" and
              previous_book.title[-4:-3] == "2"):
                return "SCP Foundation: Tome 3.01"   
        elif len(previous_book.allpages) < 500:
                return previous_book.title
        else:
                return increment_title(previous_book.title)
    def node_with_text(book, text):
        for k in book.toc.iter("navPoint"):
            if text == k.find("navLabel").find("text").text:
                return k
    author_overrides = {i.select("td")[0].text: i.select("td")[1].text for i in
                        bs4(requests.get("http://05command.wikidot."
                        "com/alexandra-rewrite").text).select("tr")}
    book = Epub("SCP Foundation: Tome 1.01")
    add_static_pages(book)
    book.chapters = []
    for i in yield_pages():
        if book.title != goes_in_book(book, i):
            add_attributions(book, author_overrides)
            book.save(book.title)
            book = Epub(goes_in_book(book, i))
            add_static_pages(book)
            book.chapters = []
        c_up = None
        for c in i.chapter.split("/"):
            if not c in [i["title"] for i in book.allpages]:
                print(c)
                p = Page()
                p.title = c
                p.data = "<div class='title2'>" + c + "</div>"
                book.add_page(p, node_with_text(book, c_up))
                book.chapters.append(c)
            c_up = c
        book.add_page(i, node_with_text(book, c_up))
    add_attributions(book, author_overrides)
    book.save(book.title)

main()
