"""Run tracker OCR with a per-process OpenMP limit, without changing app environment."""
import errno
import os
import shlex
import subprocess
import sys

from pytesseract import pytesseract


def _run_ocr(image, extension, lang=None, config=''):
    # pytesseract is pinned in requirements.txt; use its image preparation and
    # cleanup so its handling of arrays, temporary files and encodings stays intact.
    with pytesseract.save(image) as (output_base, input_filename):
        args = [pytesseract.tesseract_cmd, input_filename, output_base]
        if lang is not None:
            args.extend(('-l', lang))
        if config:
            args.extend(shlex.split(config, posix=sys.platform != 'win32'))
        if extension == 'txt':
            args.append('txt')
        options = pytesseract.subprocess_args()
        environment = dict(os.environ)
        environment.setdefault('OMP_THREAD_LIMIT', '1')
        options['env'] = environment
        try:
            process = subprocess.Popen(args, **options)
        except OSError as error:
            if error.errno == errno.ENOENT:
                raise pytesseract.TesseractNotFoundError() from error
            raise
        with pytesseract.timeout_manager(process) as error_output:
            if process.returncode:
                raise pytesseract.TesseractError(process.returncode, pytesseract.get_errors(error_output))
        return pytesseract._read_output(output_base + '.' + extension)


def image_to_string(image, lang=None, config=''):
    return _run_ocr(image, 'txt', lang, config)


def image_to_data(image, lang=None, config=''):
    if pytesseract.get_tesseract_version(cached=True) < pytesseract.TESSERACT_MIN_VERSION:
        raise pytesseract.TSVNotSupported()
    tsv = _run_ocr(image, 'tsv', lang, '-c tessedit_create_tsv=1 ' + config.strip())
    return pytesseract.file_to_dict(tsv, '\t', -1)
