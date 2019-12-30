#!/usr/bin/env python3

import shutil
from typing import Iterable
from sh import lsusb, scanadf, convert, img2pdf, pdfarranger
import tempfile
import os
from threading import Semaphore, Lock
import click
from yaspin import yaspin
from yaspin.spinners import Spinners

processes = []
processes_lock = Lock()
pool = Semaphore(4)


def done(cmd, *_):
    pool.release()
    processes_lock.acquire()
    try:
        processes.remove(cmd)
    except ValueError:
        pass
    processes_lock.release()


@click.command()
@click.option('--resolution', '-r', type=click.Choice(('100', '150', '200', '300', '400', '600')),
              default='200', show_default=True)
@click.option('--color', '-c', type=click.Choice(('monochrome', 'grayscale', 'truecolor'), case_sensitive=False),
              default='grayscale', show_default=True)
@click.option('--duplex', '-d', is_flag=True)
@click.option('--deskew/--no-deskew', default=True)
@click.option('--trim/--no-trim', default=True)
@click.option('--batch', '-b', is_flag=True)
def main(resolution: int, color: str, duplex: bool, deskew: bool, trim: bool, batch: bool):
    result = str(lsusb('-d', '04f9:'))
    device: str
    bus: str
    (_, bus, _, device) = result.partition(':')[0].split(' ')
    sane_model = 'BrotherADS2700'
    sane_device = f'{sane_model}:libusb:{bus}:{device}'

    working_dir = tempfile.mkdtemp()
    mode_map = {
        'monochrome': 'Black & White',
        'grayscale': 'Gray',
        'truecolor': '24 bit Color'
    }
    option_mode = mode_map[color]

    scan_line = 'Scanned document '
    final_images = []

    batch_number = 0
    batch_complete = False
    while not batch_complete:
        scanner_output = os.path.join(working_dir, f'scanned-{batch_number}-%d.pnm')
        option_source = 'Automatic Document Feeder(left aligned,Duplex)' if duplex \
                        else 'Automatic Document Feeder(left aligned)'
        scan_iter: Iterable[str] = scanadf('--device-name', sane_device, '--mode', option_mode, '--resolution',
                                           resolution,
                                           '--output-file', scanner_output, '--source', option_source, _iter='err')

        with yaspin(text='Scanning...') as spin:
            for line in scan_iter:
                line = line.rstrip()
                if line.startswith(scan_line):
                    file_name = line[len(scan_line):]
                    out_file_name = file_name.replace('scanned', 'cleaned').replace('.pnm', '.png')

                    convert_args = [file_name, '-fuzz', '20%']
                    if trim:
                        convert_args.append('-trim')
                    if deskew:
                        convert_args.extend(('-deskew', '30%'))
                    convert_args.extend(('+repage', out_file_name))

                    pool.acquire()
                    process = convert(*convert_args, _bg=True, _done=done)
                    processes_lock.acquire()
                    processes.append(process)
                    processing_count = len(processes)
                    processes_lock.release()

                    final_images.append(out_file_name)
                    spin.text = f'Scanning... {len(final_images)} scanned.'
                    if processing_count > 0:
                        spin.text += f' Processing {processing_count}...'
            spin.text = 'Scanning complete.'
            spin.green.ok('✔')

        processes_lock.acquire()
        processes_remaining = list(processes)
        processes_lock.release()
        with yaspin(text='Processing...') as spin:
            if len(processes_remaining) > 0:
                i = 0
                for process in processes_remaining:
                    spin.text = f'Processing {len(processes_remaining) - i}...'
                    process.wait()
                    i += 1
            spin.text = 'Processing complete.'
            spin.green.ok('✔')
        processes.clear()

        if not batch:
            batch_complete = True
        else:
            batch_number += 1
            while True:
                value = click.prompt('Next batch (Single/Duplex/Finished):', type=click.Choice(('s', 'd', 'F'), case_sensitive=False), default='F').lower()
                if value == 'f':
                    batch_complete = True
                elif value == 'd':
                    duplex = True
                elif value == 's':
                    duplex = False
                else:
                    continue
                break

    input_pdf = os.path.join(working_dir, 'cleaned.pdf')

    with yaspin(text='Creating PDF...') as spin:
        img2pdf(*final_images, '-o', input_pdf)
        spin.text = 'PDF complete.'
        spin.green.ok('✔')

    with yaspin(text='Waiting for PDF arrangement...', spinner=Spinners.clock) as spin:
        pdfarranger(input_pdf)
        spin.text = 'PDF arranger closed.'
        spin.green.ok('✔')

    if click.confirm(f'Remove temporary files ({working_dir})?', default=True, show_default=True):
        with yaspin(text='Cleaning up...') as spin:
            shutil.rmtree(working_dir)
            spin.text = 'Clean up complete.'
            spin.green.ok('✔')


if __name__ == "__main__":
    main()
