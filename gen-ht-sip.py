#!/usr/bin/python3

from pprint import pformat
import argparse
import glob
import hashlib
import logging
import os
import re
import regex
import shlex
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import util
import yaml


RSTAR_HOME = "/content/prod/rstar"

RUBY_DEFAULT = "3.0.0@ht_sip_validator"


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
    logging.debug("Running cmd: %s", shlex_join(cmd))
    subprocess.run(cmd, check=True)


def do_rvm_cmd(cmd_list, ruby_version):
    cmd_str = shlex_join(cmd_list)
    bash_command = f"""
    rvm use {ruby_version}
    {cmd_str}
    """
    do_cmd(["bash", "--login", "-c", bash_command])


def get_magick_cmd():
    magick_cmd = None
    for cmd in ("magick", "convert"):
        if shutil.which(cmd):
            magick_cmd = cmd
            break
    if not magick_cmd:
        sys.exit("ImageMagick is not installed.")
    return magick_cmd


def remove_pattern_from_file(pattern, input_file):
    output_file = input_file + ".tmp"
    with open(input_file) as in_fh, open(output_file, "w") as out_fh:
        for line in in_fh:
            line = line.rstrip("\n")
            out_fh.write(regex.sub(pattern, "", line) + "\n")
    os.rename(output_file, input_file)


def remove_control_chars(input_file):
    remove_pattern_from_file(r"\p{C}", input_file)


def shlex_join(split_command):
    """Return a shell-escaped string from *split_command*."""
    return " ".join(shlex.quote(arg) for arg in split_command)


def validate_rvm_env_format(value):
    """
    Validates that the input matches the expected
    RVM format: ruby_version@gemset

    e.g., 2.7.2@mygemset or ruby-3.1.0@my_gemset
    """
    pattern = r"^(?:ruby-)?\d+\.\d+\.\d+@[\w\-.]+$"
    if not re.match(pattern, value):
        raise argparse.ArgumentTypeError(
            "Expected format: ruby_version@gemset (e.g., 2.7.2@mygemset or"
            " ruby-3.1.0@gem-set)"
        )
    return value


def main():
    script_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
    meta_file = os.path.join(script_dir, "meta.yml")
    magick = get_magick_cmd()
    tessdata_dir = os.path.join(os.path.expanduser("~"), "tessdata_best")

    parser = argparse.ArgumentParser(description="Generate SIP for HathiTrust")
    parser.add_argument("input_dir", type=validate_dirpath)
    parser.add_argument("-m", "--max-pages", type=int)
    parser.add_argument(
        "-r",
        "--ruby-version",
        default=RUBY_DEFAULT,
        type=validate_rvm_env_format,
    )
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

    max_pages = args.max_pages if args.max_pages else len(img_files)

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
            for i, img_file in enumerate(img_files[:max_pages], start=1):
                basename = f"{i:08d}"
                logging.debug("basename: %s", basename)
                output_base = os.path.join(sip_dir, basename)

                cleaned_img = output_base + ".tif"
                do_cmd([magick, img_file + "[0]", cleaned_img])

                tesseract = [
                    "tesseract",
                    cleaned_img,
                    output_base,
                    "--tessdata-dir",
                    tessdata_dir,
                ]
                do_cmd(tesseract)
                do_cmd(tesseract + ["hocr"])
                os.rename(output_base + ".hocr", output_base + ".html")

                for ext in [".tif", ".txt", ".html"]:
                    filename = basename + ext
                    full_path = os.path.join(sip_dir, filename)
                    if ext == ".tif":
                        page_data[filename] = {"orderlabel": str(i)}
                    else:
                        remove_control_chars(full_path)
                        remove_pattern_from_file(
                            rf"{sip_dir}{os.sep}", full_path
                        )
                    chks_out.write(f"{calculate_md5(full_path)} {filename}\n")

            meta["pagedata"] = page_data

            meta_base = "meta.yml"
            meta_file = os.path.join(sip_dir, meta_base)
            logging.debug(f"new meta file: {meta_file}")
            with open(meta_file, "w") as meta_fh:
                meta_fh.write(meta_str.strip() + "\n")
                meta_fh.write(
                    yaml.dump(
                        {"pagedata": page_data},
                        indent=4,
                        default_flow_style=None,
                    )
                )
            with open(meta_file) as meta_fh:
                logging.debug("meta file:\n%s", meta_fh.read())
            chks_out.write(f"{calculate_md5(meta_file)} {meta_base}\n")

        output_zip_file = os.path.join(tmp_base, barcode)
        shutil.make_archive(output_zip_file, "zip", sip_dir)

    output_zip_file = f"{output_zip_file}.zip"
    size_gb = os.path.getsize(output_zip_file) / (1024**3)
    logging.debug(f"file size: {size_gb:.2f} GB")

    orig_dir = os.getcwd()
    validator_dir = os.path.join(os.path.expanduser("~"), "ht_sip_validator")
    os.chdir(validator_dir)
    do_rvm_cmd(
        ["bundle", "exec", "ruby", "bin/validate_sip", output_zip_file],
        args.ruby_version,
    )
    os.chdir(orig_dir)

    if size_gb > 15:
        util.split_zip(output_zip_file)


if __name__ == "__main__":
    main()
