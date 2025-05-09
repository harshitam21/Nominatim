# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of Nominatim. (https://nominatim.org)
#
# Copyright (C) 2025 by the Nominatim developer community.
# For a full list of authors see the git log.
"""
Tests for SQL preprocessing.
"""
import pytest
import pytest_asyncio  # noqa

from nominatim_db.db.sql_preprocessor import SQLPreprocessor


@pytest.fixture
def sql_factory(tmp_path):
    def _mk_sql(sql_body):
        (tmp_path / 'test.sql').write_text("""
          CREATE OR REPLACE FUNCTION test() RETURNS TEXT
          AS $$
          BEGIN
            {}
          END;
          $$ LANGUAGE plpgsql IMMUTABLE;""".format(sql_body))
        return 'test.sql'

    return _mk_sql


@pytest.mark.parametrize("expr,ret", [
    ("'a'", 'a'),
    ("'{{db.partitions|join}}'", '012'),
    ("{% if 'country_name' in db.tables %}'yes'{% else %}'no'{% endif %}", "yes"),
    ("{% if 'xxx' in db.tables %}'yes'{% else %}'no'{% endif %}", "no"),
    ("'{{db.tablespace.address_data}}'", ""),
    ("'{{db.tablespace.search_data}}'", 'TABLESPACE "dsearch"'),
    ("'{{db.tablespace.address_index}}'", 'TABLESPACE "iaddress"'),
    ("'{{db.tablespace.aux_data}}'", 'TABLESPACE "daux"')
    ])
def test_load_file_simple(sql_preprocessor_cfg, sql_factory,
                          temp_db_conn, temp_db_cursor, monkeypatch,
                          expr, ret):
    monkeypatch.setenv('NOMINATIM_TABLESPACE_SEARCH_DATA', 'dsearch')
    monkeypatch.setenv('NOMINATIM_TABLESPACE_ADDRESS_INDEX', 'iaddress')
    monkeypatch.setenv('NOMINATIM_TABLESPACE_AUX_DATA', 'daux')
    sqlfile = sql_factory("RETURN {};".format(expr))

    SQLPreprocessor(temp_db_conn, sql_preprocessor_cfg).run_sql_file(temp_db_conn, sqlfile)

    assert temp_db_cursor.scalar('SELECT test()') == ret


def test_load_file_with_params(sql_preprocessor, sql_factory, temp_db_conn, temp_db_cursor):
    sqlfile = sql_factory("RETURN '{{ foo }} {{ bar }}';")

    sql_preprocessor.run_sql_file(temp_db_conn, sqlfile, bar='XX', foo='ZZ')

    assert temp_db_cursor.scalar('SELECT test()') == 'ZZ XX'


@pytest.mark.asyncio
async def test_load_parallel_file(dsn, sql_preprocessor, tmp_path, temp_db_cursor):
    (tmp_path / 'test.sql').write_text("""
        CREATE TABLE foo (a TEXT);
        CREATE TABLE foo2(a TEXT);""" + "\n---\nCREATE TABLE bar (b INT);")

    await sql_preprocessor.run_parallel_sql_file(dsn, 'test.sql', num_threads=4)

    assert temp_db_cursor.table_exists('foo')
    assert temp_db_cursor.table_exists('foo2')
    assert temp_db_cursor.table_exists('bar')
