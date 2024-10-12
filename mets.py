from lxml import etree as ET
import logging
import re
import util


class SourceEntityMets:
    def __init__(self, mets_file):
        logging.debug(f"METS file: {mets_file}")
        self.mets_file = mets_file

        nsmap = {
            "m": "http://www.loc.gov/METS/",
            "xlink": "http://www.w3.org/1999/xlink",
        }

        self.tree = ET.parse(mets_file)
        logging.debug("tree: %s", self.tree)

        self.root = self.tree.getroot()
        logging.debug("root: %s", self.root)

        for namespace in nsmap.values():
            util.remove_namespace(self.root, namespace)
            logging.debug(self.root)

        ET.cleanup_namespaces(self.tree)

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
