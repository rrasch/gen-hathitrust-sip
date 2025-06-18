#!/usr/bin/python3

from pprint import pformat
import argparse
import glob
import hashlib
import logging
import os
import regex
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import util
import yaml


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


def validate_dirpath(dirpath: str) -> str:
    """Validates a dirpath and returns it if valid."""
    if not os.path.isdir(dirpath):
        raise argparse.ArgumentTypeError(f"Directory not found: '{dirpath}'")
    return os.path.realpath(dirpath)


def do_cmd(cmd):
    subprocess.run(cmd, check=True)


def main():
    script_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
    meta_file = os.path.join(script_dir, "meta.yml")

    parser = argparse.ArgumentParser(description="Generate SIP for HathiTrust")
    parser.add_argument("input_dir", type=validate_dirpath)
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

    barcode = os.path.basename(args.input_dir)
    logging.debug("barcode: %s", barcode)

    img_files = sorted(glob.glob(os.path.join(args.input_dir, "*.tif")))
    logging.debug("img_files:\n%s", pformat(img_files))

    with open(meta_file) as f:
        meta = yaml.safe_load(f)
        f.seek(0)
        meta_str = f.read()
    logging.debug("meta file contents: %s", pformat(meta))

    tmp_base = os.path.join(RSTAR_HOME, "tmp", os.getlogin())
    with tempfile.TemporaryDirectory(dir=tmp_base) as tmpdir:
        sip_dir = os.path.join(tmpdir, barcode)
        os.mkdir(sip_dir)

        page_data = {}

        checksum_file = os.path.join(sip_dir, "checksum.md5")
        with open(checksum_file, "w") as chks_out:
            for i, img_file in enumerate(img_files, start=1):
                basename = f"{i:08d}"
                logging.debug("basename: %s", basename)
                output_base = os.path.join(sip_dir, basename)

                cleaned_img = output_base + ".tif"
                do_cmd(["convert", img_file + "[0]", cleaned_img])
                do_cmd(["tesseract", cleaned_img, output_base])
                do_cmd(["tesseract", cleaned_img, output_base, "hocr"])
                os.rename(output_base + ".hocr", output_base + ".html")

                for ext in [".tif", ".txt", ".html"]:
                    filename = basename + ext
                    full_path = os.path.join(sip_dir, filename)
                    if ext == ".tif":
                        page_data[filename] = {"orderlabel": str(i)}
                    chks_out.write(f"{calculate_md5(full_path)} {filename}\n")

            meta["pagedata"] = page_data

            meta_base = "meta.yml"
            meta_file = os.path.join(sip_dir, meta_base)
            logging.debug(f"new meta file: {meta_file}")
            with open(meta_file, "w") as meta_fh:
                meta_fh.write(meta_str.strip() + "\n")
                meta_fh.write(yaml.dump({"pagedata": page_data}, indent=4))
            chks_out.write(f"{calculate_md5(meta_file)} {meta_base}\n")

        output_zip_file = os.path.join(tmp_base, barcode)
        shutil.make_archive(output_zip_file, "zip", sip_dir)

    output_zip_file = f"{output_zip_file}.zip"
    size_gb = os.path.getsize(output_zip_file) / (1024**3)
    logging.debug(f"file size: {size_gb:.2f} GB")

    orig_dir = os.getcwd()
    validator_dir = os.path.join(os.path.expanduser("~"), "ht_sip_validator")
    os.chdir(validator_dir)
    do_cmd(["bundle", "exec", "ruby", "bin/validate_sip", output_zip_file])
    os.chdir(orig_dir)

    if size_gb > 15:
        util.split_zip(output_zip_file)


if __name__ == "__main__":
    main()
