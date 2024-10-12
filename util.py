from lxml import etree as ET
import os
import subprocess
import zipfile


def change_ext(filename, new_ext) -> str:
    basename, ext = os.path.splitext(filename)
    return f"{basename}{new_ext}"


def remove_namespace(doc, namespace) -> None:
    """Remove namespace in the passed document in place."""
    ns = "{%s}" % namespace
    nsl = len(ns)
    for elem in doc.iter():
        if isinstance(elem, ET._ProcessingInstruction):
            continue
        if elem.tag.startswith(ns):
            elem.tag = elem.tag[nsl:]
        for attr_name in elem.attrib:
            if attr_name.startswith(ns):
                elem.attrib[attr_name[nsl:]] = elem.attrib.pop(attr_name)


def split_zip_7z(input_zip_file, output_dir):
    cmd = ["7z", "-v10g", "a", input_zip_file, output_dir]
    subprocess.run(cmd)


def split_zip(input_zip_file, output_dir, max_size):
    """
    Splits a large zip file into smaller zip files.

    :param input_zip_file: Path to the input zip file.
    :param output_dir: Directory to store the smaller zip files.
    :param max_size: Maximum size for each zip part in bytes.
    """
    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)

    with zipfile.ZipFile(input_zip_file, "r") as input_zip:
        file_list = input_zip.namelist()  # List of files in the zip
        current_size = 0
        part_num = 1
        part_zip = None

        for file_name in file_list:
            # Get file info and its data
            file_info = input_zip.getinfo(file_name)
            file_size = file_info.file_size

            # Create a new part if current size exceeds max_size or if this is the first file
            if part_zip is None or (current_size + file_size > max_size):
                if part_zip:
                    part_zip.close()

                part_zip_name = os.path.join(output_dir, f"part_{part_num}.zip")
                part_zip = zipfile.ZipFile(
                    part_zip_name, "w", zipfile.ZIP_DEFLATED
                )
                part_num += 1
                current_size = 0  # Reset size for new part

            # Write the file to the current part zip
            part_zip.writestr(file_info, input_zip.read(file_name))
            current_size += file_size

        # Close the last part
        if part_zip:
            part_zip.close()
