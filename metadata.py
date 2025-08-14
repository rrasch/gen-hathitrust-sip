from lxml import etree as ET
import logging
import os
import re
import util


class MODSFileNotFound(Exception):
    pass


class Meta:
    nsmap = {}

    def __init__(self, filepath):
        self.filepath = filepath

        self.tree = ET.parse(filepath)
        logging.debug("tree: %s", self.tree)

        self.root = self.tree.getroot()
        logging.debug("root: %s", self.root)

        for namespace in self.nsmap.values():
            util.remove_namespace(self.root, namespace)

        ET.cleanup_namespaces(self.tree)

    def _get_text(self, expr):
        results = self.root.xpath(expr)
        if results:
            return results[0].text
        else:
            return ""


class MODS(Meta):
    nsmap = {
        "m": "http://www.loc.gov/mods/v3",
    }

    def __init__(self, filepath, lang=None):
        super().__init__(filepath)
        self.lang = lang

    def title(self):
        xpath = "/mods/titleInfo[not(@type='uniform')"
        if self.lang:
            xpath += f" and @script='{self.lang}'"
        xpath += "]"
        non_sort = self._get_text(f"{xpath}/nonSort")
        title = self._get_text(f"{xpath}/title")
        return non_sort + title


class SourceEntityMETS(Meta):
    nsmap = {
        "m": "http://www.loc.gov/METS/",
        "xlink": "http://www.w3.org/1999/xlink",
    }

    def id(self):
        return self.root.xpath("/mets/@OBJID")[0]

    def get_file_ids(self):
        file_id_list = []
        xpath = "/mets/structMap/div/div/div[@ORDER]"
        for div in sorted(
            self.root.xpath(xpath), key=lambda d: int(d.get("ORDER"))
        ):
            logging.debug("order: %s", div.get("ORDER"))
            file_id = div.xpath("./fptr/@FILEID")[0]
            file_id = re.sub(r"^f-", "", file_id)
            file_id = re.sub(r"_[md]$", "", file_id)
            file_id_list.append(file_id)
        return file_id_list

    def get_mods_file(self):
        mods_file = self.root.xpath("//mdRef[@MDTYPE='MODS']/@href")
        if not mods_file:
            raise MODSFileNotFound("Could not find MODS file")
        return os.path.join(os.path.dirname(self.filepath), mods_file[0])
