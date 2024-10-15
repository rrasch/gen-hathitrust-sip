#!/usr/bin/python3

from pprint import pformat
import argparse
import hashlib
import logging
import mets
import os
import pymods
import re
import regex
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import util
import yaml


HATHI_EXT = {
    "_d.jp2": ".jp2",
    "_ocr.txt": ".txt",
    "_ocr.hocr": ".html",
}

RSTAR_HOME = "/content/prod/rstar"


def calculate_md5(filename):
    """Calculates the MD5 checksum of a file."""

    hash_md5 = hashlib.md5()
    with open(filename, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def remove_control_chars(input_file, output_file):
    with open(input_file) as in_fh, open(output_file, "w") as out_fh:
        for line in in_fh:
            out_fh.write(regex.sub(r"\p{C}", "", line) + "\n")


def main():
    script_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
    meta_file = os.path.join(script_dir, "meta.yml")
    barcodes_file = os.path.join(script_dir, "barcodes.yml")

    parser = argparse.ArgumentParser(description="Generate SIP for HathiTrust")
    parser.add_argument("id", help="Object identifier")
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debugging"
    )
    args = parser.parse_args()

    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        format="%(asctime)s|%(levelname)s: %(message)s",
        datefmt="%m/%d/%Y %I:%M:%S %p",
        level=level,
    )

    match = re.search(r"^([a-z]+)_([a-z]+)(\d{6})$", args.id)
    if not match:
        sys.exit(f"Invalid identifier '{args.id}'")

    partner = match.group(1)
    collection = match.group(2)

    with open(meta_file) as f:
        meta = yaml.safe_load(f)
        f.seek(0)
        meta_str = f.read()
    logging.debug("meta file contents: %s", pformat(meta))

    with open(barcodes_file) as f:
        barcodes = yaml.safe_load(f)
    logging.debug("barcodes: %s", pformat(barcodes))

    rstar_dir = os.path.join(
        RSTAR_HOME, "content", partner, collection, "wip", "se", args.id
    )
    logging.debug(f"rstar dir: {rstar_dir}")

    mets_file = os.path.join(rstar_dir, "data", f"{args.id}_mets.xml")
    logging.debug(f"METS file: {mets_file}")

    source_mets = mets.SourceEntityMets(mets_file)

    mods_file = source_mets.get_mods_file()
    logging.debug(f"MODS file: {mods_file}")
    mods = mets.MODS(mods_file)
    title = mods.title()
    logging.debug(f"title: {title}")

    mods_record = next(pymods.MODSReader(mods_file))
    logging.debug(mods_record.titles)

    tmp_base = os.path.join(RSTAR_HOME, "tmp", os.getlogin())
    with tempfile.TemporaryDirectory(dir=tmp_base) as tmpdir:
        sip_dir = os.path.join(tmpdir, args.id)
        os.mkdir(sip_dir)

        page_data = {}

        checksum_file = os.path.join(sip_dir, "checksum.md5")
        chks_out = open(checksum_file, "w")
        for i, file_id in enumerate(source_mets.get_file_ids(), start=1):
            for src_ext in HATHI_EXT:
                src_file = os.path.join(rstar_dir, "aux", f"{file_id}{src_ext}")
                dst_base = f"{i:08d}{HATHI_EXT[src_ext]}"
                dst_file = os.path.join(sip_dir, dst_base)
                if HATHI_EXT[src_ext] == ".jp2":
                    os.symlink(src_file, dst_file)
                    page_data[dst_base] = {"orderlabel": str(i)}
                else:
                    remove_control_chars(src_file, dst_file)
                chks_out.write(f"{calculate_md5(dst_file)} {dst_base}\n")

        meta["pagedata"] = page_data

        meta_base = "meta.yml"
        meta_file = os.path.join(sip_dir, meta_base)
        logging.debug(f"new meta file: {meta_file}")
        with open(meta_file, "w") as meta_fh:
            meta_fh.write(meta_str.strip() + "\n")
            meta_fh.write(yaml.dump({"pagedata": page_data}))
        chks_out.write(f"{calculate_md5(meta_file)} {meta_base}\n")
        chks_out.close()

        output_zip_file = os.path.join(tmp_base, str(barcodes[args.id]))
        shutil.make_archive(output_zip_file, "zip", sip_dir)

        output_zip_file = f"{output_zip_file}.zip"
        size_gb = os.path.getsize(output_zip_file) / (1024**3)
        logging.debug(f"file size: {size_gb:.2f} GB")

        orig_dir = os.getcwd()
        validator_dir = os.path.join(
            os.path.expanduser("~"), "ht_sip_validator"
        )
        os.chdir(validator_dir)
        subprocess.run(
            ["bundle", "exec", "ruby", "bin/validate_sip", output_zip_file],
            check=True,
        )
        os.chdir(orig_dir)

        if size_gb > 15:
            util.split_zip(output_zip_file)


if __name__ == "__main__":
    main()
