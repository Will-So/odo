from __future__ import absolute_import, division, print_function

import pytest
paramiko = pytest.importorskip('paramiko')

import pandas as pd
import numpy as np
import uuid
import re
import os

from into.utils import tmpfile, filetext
from into.directory import _Directory, Directory
from into.backends.ssh import SSH, resource, ssh_pattern, sftp, drop, connect
from into.backends.csv import CSV
from into import into, discover, CSV, JSONLines, JSON
from into.temp import _Temp, Temp
import socket

try:
    ssh = connect(hostname='localhost')
except socket.error:
    pytest.importorskip('does_not_exist')


def test_resource():
    r = resource('ssh://joe@localhost:/path/to/myfile.csv')
    assert isinstance(r, SSH(CSV))
    assert r.path == '/path/to/myfile.csv'
    assert r.auth['hostname'] == 'localhost'
    assert r.auth['username'] == 'joe'


def test_connect():
    a = connect(hostname='localhost')
    b = connect(hostname='localhost')
    assert a is b

    a.close()

    c = connect(hostname='localhost')
    assert a is c
    assert c.get_transport() and c.get_transport().is_active()


def test_resource_directory():
    r = resource('ssh://joe@localhost:/path/to/')
    assert issubclass(r.subtype, _Directory)

    r = resource('ssh://joe@localhost:/path/to/*.csv')
    assert r.subtype == Directory(CSV)
    assert r.path == '/path/to/'


def test_discover():
    with filetext('name,balance\nAlice,100\nBob,200') as fn:
        local = CSV(fn)
        remote = SSH(CSV)(fn, hostname='localhost')

        assert discover(local) == discover(remote)


def test_discover_from_resource():
    with filetext('name,balance\nAlice,100\nBob,200', extension='csv') as fn:
        local = CSV(fn)
        remote = resource('ssh://localhost:' + fn)

        assert discover(local) == discover(remote)


def test_ssh_pattern():
    uris = ['localhost:myfile.csv',
            '127.0.0.1:/myfile.csv',
            'user@127.0.0.1:/myfile.csv',
            'user@127.0.0.1:/*.csv',
            'user@127.0.0.1:/my-dir/my-file3.csv']
    for uri in uris:
        assert re.match(ssh_pattern, uri)


def test_copy_remote_csv():
    with tmpfile('csv') as target:
        with filetext('name,balance\nAlice,100\nBob,200',
                      extension='csv') as fn:
            csv = resource(fn)

            uri = 'ssh://localhost:%s.csv' % str(uuid.uuid1())
            scsv = into(uri, csv)

            assert isinstance(scsv, SSH(CSV))
            assert discover(scsv) == discover(csv)

            # Round trip
            csv2 = into(target, scsv)
            assert into(list, csv) == into(list, csv2)

            drop(uri)


def test_drop():
    with filetext('name,balance\nAlice,100\nBob,200', extension='csv') as fn:
        with tmpfile('csv') as target:
            scsv = SSH(CSV)(target, hostname='localhost')

            assert not os.path.exists(target)

            conn = sftp(**scsv.auth)
            conn.put(fn, target)

            assert os.path.exists(target)

            drop(scsv)
            drop(scsv)

            assert not os.path.exists(target)


def test_drop_of_csv_json_lines_use_ssh_version():
    from into.backends.ssh import drop_ssh
    for typ in [CSV, JSON, JSONLines]:
        assert drop.dispatch(SSH(typ)) == drop_ssh


def test_temp_ssh_files():
    with filetext('name,balance\nAlice,100\nBob,200', extension='csv') as fn:
        csv = CSV(fn)
        scsv = into(Temp(SSH(CSV)), csv, hostname='localhost')
        assert discover(csv) == discover(scsv)

        assert isinstance(scsv, _Temp)


def test_convert_through_temporary_local_storage():
    with filetext('name,quantity\nAlice,100\nBob,200', extension='csv') as fn:
        csv = CSV(fn)
        df = into(pd.DataFrame, csv)
        scsv = into(Temp(SSH(CSV)), csv, hostname='localhost')

        assert into(list, csv) == into(list, scsv)

        scsv2 = into(Temp(SSH(CSV)), df, hostname='localhost')
        assert into(list, scsv2) == into(list, df)

        sjson = into(Temp(SSH(JSONLines)), df, hostname='localhost')
        assert (into(np.ndarray, sjson) == into(np.ndarray, df)).all()
