# -*- coding: utf-8 -*-
"""Command to install a pseudo potential family."""
import os
import shutil
import tempfile

import click

from aiida.cmdline.utils import decorators, echo
from aiida.cmdline.params import options as options_core
from aiida.cmdline.params import types

from .params import options
from .root import cmd_root

URL_SSSP_BASE = 'https://legacy-archive.materialscloud.org/file/2018.0001/v4/'


@cmd_root.group('install')
def cmd_install():
    """Install pseudo potential families."""


@cmd_install.command('family')
@click.argument('archive', type=types.FileOrUrl(mode='rb'))
@click.argument('label', type=click.STRING)
@options_core.DESCRIPTION(help='Description for the family.')
@options.ARCHIVE_FORMAT()
@options.FAMILY_TYPE()
@options.TRACEBACK()
@decorators.with_dbenv()
def cmd_install_family(archive, label, description, archive_format, family_type, traceback):  # pylint: disable=too-many-arguments
    """Install a standard pseudo potential family from an ARCHIVE on the local file system or from a URL.

    The command will attempt to infer the archive format from the filename extension of the ARCHIVE. If this fails, the
    archive format can be specified explicitly with the archive format option, which will also display which formats
    are supported.

    By default, the command will create a base `PseudoPotentialFamily`, but the type can be changed with the family
    type option. If the base type is used, the pseudo potential files in the archive *have* to have filenames that
    strictly follow the format `ELEMENT.EXTENSION`, because otherwise the element cannot be determined automatically.
    """
    from .utils import attempt, create_family_from_archive

    # The `archive` is now either a `http.client.HTTPResponse` or a normal filelike object, so we get the original file
    # name in a different way.
    try:
        suffix = os.path.basename(archive.url)
    except AttributeError:
        suffix = os.path.basename(archive.name)

    # Write the content of the archive to a temporary file, because `create_family_from_archive` does currently not
    # accept filelike objects because the underlying `shutil.unpack_archive` does not. Likewise, `unpack_archive` will
    # attempt to deduce the archive format from the filename extension, so it is important we maintain the original
    # filename. Of course if this fails, users can specify the archive format explicitly wiht the corresponding option.
    with tempfile.NamedTemporaryFile(mode='w+b', suffix=suffix) as handle:
        shutil.copyfileobj(archive, handle)
        handle.flush()

        with attempt('unpacking archive and parsing pseudos... ', include_traceback=traceback):
            family = create_family_from_archive(family_type, label, handle.name, fmt=archive_format)

    family.description = description
    echo.echo_success('installed `{}` containing {} pseudo potentials'.format(label, family.count()))


@cmd_install.command('sssp')
@options.VERSION(type=click.Choice(['1.0', '1.1']), default='1.1')
@options.FUNCTIONAL(type=click.Choice(['PBE', 'PBEsol']), default='PBE')
@options.PROTOCOL(type=click.Choice(['efficiency', 'precision']), default='efficiency')
@options.TRACEBACK()
@decorators.with_dbenv()
def cmd_install_sssp(version, functional, protocol, traceback):
    """Install an SSSP configuration.

    The SSSP configuration will be automatically downloaded from the Materials Cloud Archive entry to create a new
    `SsspFamily`.
    """
    # pylint: disable=too-many-locals
    import requests

    from aiida.common.files import md5_file
    from aiida.orm import QueryBuilder

    from aiida_pseudo import __version__
    from aiida_pseudo.groups.family import SsspConfiguration, SsspFamily
    from .utils import attempt, create_family_from_archive

    configuration = SsspConfiguration(version, functional, protocol)
    label = SsspFamily.format_configuration_label(configuration)
    description = 'SSSP v{} {} {} installed with aiida-pseudo v{}'.format(*configuration, __version__)

    if configuration not in SsspFamily.valid_configurations:
        echo.echo_critical('{} {} {} is not a valid SSSP configuration'.format(*configuration))

    if QueryBuilder().append(SsspFamily, filters={'label': label}).first():
        echo.echo_critical('{}<{}> is already installed'.format(SsspFamily.__name__, label))

    with tempfile.TemporaryDirectory() as dirpath:

        url_archive = '{}/SSSP_{}_{}_{}.tar.gz'.format(URL_SSSP_BASE, version, functional, protocol)
        filepath_archive = os.path.join(dirpath, 'archive.tar.gz')

        with attempt('downloading selected pseudo potentials archive... ', include_traceback=traceback):
            response = requests.get(url_archive)
            response.raise_for_status()
            with open(filepath_archive, 'wb') as handle:
                handle.write(response.content)
                handle.flush()
                description += '\nArchive pseudos md5: {}'.format(md5_file(filepath_archive))

        with attempt('unpacking archive and parsing pseudos... ', include_traceback=traceback):
            family = create_family_from_archive(SsspFamily, label, filepath_archive)

        family.description = description
        echo.echo_success('installed `{}` containing {} pseudo potentials'.format(label, family.count()))