# -*- coding: utf-8 -*-
"""Windows EventLog resources database reader."""

import os
import re
import sqlite3


class Sqlite3DatabaseFile(object):
  """Class that defines a sqlite3 database file."""

  _HAS_TABLE_QUERY = (
      'SELECT name FROM sqlite_master '
      'WHERE type = "table" AND name = "{0:s}"')

  def __init__(self):
    """Initializes the database file object."""
    super(Sqlite3DatabaseFile, self).__init__()
    self._connection = None
    self._cursor = None
    self.filename = None
    self.read_only = None

  def Close(self):
    """Closes the database file.

    Raises:
      RuntimeError: if the database is not opened.
    """
    if not self._connection:
      raise RuntimeError('Cannot close database not opened.')

    # We need to run commit or not all data is stored in the database.
    self._connection.commit()
    self._connection.close()

    self._connection = None
    self._cursor = None
    self.filename = None
    self.read_only = None

  def HasTable(self, table_name):
    """Determines if a specific table exists.

    Args:
      table_name (str): table name.

    Returns:
      bool: True if the table exists.

    Raises:
      RuntimeError: if the database is not opened.
    """
    if not self._connection:
      raise RuntimeError(
          'Cannot determine if table exists database not opened.')

    sql_query = self._HAS_TABLE_QUERY.format(table_name)

    self._cursor.execute(sql_query)
    if self._cursor.fetchone():
      return True

    return False

  def GetValues(self, table_names, column_names, condition):
    """Retrieves values from a table.

    Args:
      table_names (list[str]): table names.
      column_names (list[str]): column names.
      condition (str): query condition such as
          "log_source == 'Application Error'".

    Yields:
      sqlite3.row: row.

    Raises:
      RuntimeError: if the database is not opened.
    """
    if not self._connection:
      raise RuntimeError('Cannot retrieve values database not opened.')

    if condition:
      condition = ' WHERE {0:s}'.format(condition)

    sql_query = 'SELECT {1:s} FROM {0:s}{2:s}'.format(
        ', '.join(table_names), ', '.join(column_names), condition)

    self._cursor.execute(sql_query)

    # TODO: have a look at https://docs.python.org/2/library/
    # sqlite3.html#sqlite3.Row.
    for row in self._cursor:
      yield {
          column_name: row[column_index]
          for column_index, column_name in enumerate(column_names)}

  def Open(self, filename, read_only=False):
    """Opens the database file.

    Args:
      filename (str): filename of the database.
      read_only (Optional[bool]): True if the database should be opened in
          read-only mode. Since sqlite3 does not support a real read-only
          mode we fake it by only permitting SELECT queries.

    Returns:
      bool: True if successful.

    Raises:
      RuntimeError: if the database is already opened.
    """
    if self._connection:
      raise RuntimeError('Cannot open database already opened.')

    self.filename = filename
    self.read_only = read_only

    try:
      self._connection = sqlite3.connect(filename)
    except sqlite3.OperationalError:
      return False

    if not self._connection:
      return False

    self._cursor = self._connection.cursor()
    if not self._cursor:
      return False

    return True


class WinevtResourcesSqlite3DatabaseReader(object):
  """Windows EventLog resources SQLite database reader."""

  # Message string specifiers that are considered white space.
  _WHITE_SPACE_SPECIFIER_RE = re.compile(r'(%[0b]|[\r\n])')
  # Message string specifiers that expand to text.
  _TEXT_SPECIFIER_RE = re.compile(r'%([ .!%nrt])')
  # Curly brackets in a message string.
  _CURLY_BRACKETS = re.compile(r'([\{\}])')
  # Message string specifiers that expand to a variable place holder.
  _PLACE_HOLDER_SPECIFIER_RE = re.compile(r'%([1-9][0-9]?)[!]?[s]?[!]?')

  def __init__(self):
    """Initializes a Windows EventLog resources SQLite database reader."""
    super(WinevtResourcesSqlite3DatabaseReader, self).__init__()
    self._database_file = Sqlite3DatabaseFile()
    self._string_format = 'wrc'

  def _GetEventLogProviderKey(self, log_source):
    """Retrieves the EventLog provider key.

    Args:
      log_source (str): EventLog source.

    Returns:
      str: EventLog provider key or None if not available.

    Raises:
      RuntimeError: if more than one value is found in the database.
    """
    table_names = ['event_log_providers']
    column_names = ['event_log_provider_key']
    condition = 'log_source == "{0:s}"'.format(log_source)

    values_list = list(self._database_file.GetValues(
        table_names, column_names, condition))

    number_of_values = len(values_list)
    if number_of_values == 0:
      return None

    if number_of_values == 1:
      values = values_list[0]
      return values['event_log_provider_key']

    raise RuntimeError('More than one value found in database.')

  def _GetMessage(self, message_file_key, lcid, message_identifier):
    """Retrieves a specific message from a specific message table.

    Args:
      message_file_key (int): message file key.
      lcid (int): language code identifier (LCID).
      message_identifier (int): message identifier.

    Returns:
      str: message string or None if not available.

    Raises:
      RuntimeError: if more than one value is found in the database.
    """
    table_name = 'message_table_{0:d}_0x{1:08x}'.format(message_file_key, lcid)

    has_table = self._database_file.HasTable(table_name)
    if not has_table:
      return None

    column_names = ['message_string']
    condition = 'message_identifier == "0x{0:08x}"'.format(message_identifier)

    values = list(self._database_file.GetValues(
        [table_name], column_names, condition))

    number_of_values = len(values)
    if number_of_values == 0:
      return None

    if number_of_values == 1:
      return values[0]['message_string']

    raise RuntimeError('More than one value found in database.')

  def _GetMessageFileKeys(self, event_log_provider_key):
    """Retrieves the message file keys.

    Args:
      event_log_provider_key (int): EventLog provider key.

    Yields:
      int: message file key.
    """
    table_names = ['message_file_per_event_log_provider']
    column_names = ['message_file_key']
    condition = 'event_log_provider_key == {0:d}'.format(
        event_log_provider_key)

    generator = self._database_file.GetValues(
        table_names, column_names, condition)
    for values in generator:
      yield values['message_file_key']

  def _ReformatMessageString(self, message_string):
    """Reformats the message string.

    Args:
      message_string (str): message string.

    Returns:
      str: message string in Python format() (PEP 3101) style.
    """
    def _PlaceHolderSpecifierReplacer(match_object):
      """Replaces message string place holders into Python format() style."""
      expanded_groups = []
      for group in match_object.groups():
        try:
          place_holder_number = int(group, 10) - 1
          expanded_group = '{{{0:d}:s}}'.format(place_holder_number)
        except ValueError:
          expanded_group = group

        expanded_groups.append(expanded_group)

      return ''.join(expanded_groups)

    if not message_string:
      return None

    message_string = self._WHITE_SPACE_SPECIFIER_RE.sub(r'', message_string)
    message_string = self._TEXT_SPECIFIER_RE.sub(r'\\\1', message_string)
    message_string = self._CURLY_BRACKETS.sub(r'\1\1', message_string)
    return self._PLACE_HOLDER_SPECIFIER_RE.sub(
        _PlaceHolderSpecifierReplacer, message_string)

  def Close(self):
    """Closes the database reader object."""
    self._database_file.Close()

  def GetMessage(self, log_source, lcid, message_identifier):
    """Retrieves a specific message for a specific EventLog source.

    Args:
      log_source (str): EventLog source.
      lcid (int): language code identifier (LCID).
      message_identifier (int): message identifier.

    Returns:
      str: message string or None if not available.
    """
    event_log_provider_key = self._GetEventLogProviderKey(log_source)
    if not event_log_provider_key:
      return None

    generator = self._GetMessageFileKeys(event_log_provider_key)
    if not generator:
      return None

    # TODO: cache a number of message strings.
    message_string = None
    for message_file_key in generator:
      message_string = self._GetMessage(
          message_file_key, lcid, message_identifier)

      if message_string:
        break

    if self._string_format == 'wrc':
      message_string = self._ReformatMessageString(message_string)

    return message_string

  def GetMetadataAttribute(self, attribute_name):
    """Retrieves the metadata attribute.

    Args:
      attribute_name (str): name of the metadata attribute.

    Returns:
      str: the metadata attribute or None.

    Raises:
      RuntimeError: if more than one value is found in the database.
    """
    table_name = 'metadata'

    has_table = self._database_file.HasTable(table_name)
    if not has_table:
      return None

    column_names = ['value']
    condition = 'name == "{0:s}"'.format(attribute_name)

    values = list(self._database_file.GetValues(
        [table_name], column_names, condition))

    number_of_values = len(values)
    if number_of_values == 0:
      return None

    if number_of_values == 1:
      return values[0]['value']

    raise RuntimeError('More than one value found in database.')

  def Open(self, filename):
    """Opens the database reader object.

    Args:
      filename (str): filename of the database.

    Returns:
      bool: True if successful.

    Raises:
      RuntimeError: if the version or string format of the database
                    is not supported.
    """
    if not self._database_file.Open(filename, read_only=True):
      return False

    version = self.GetMetadataAttribute('version')
    if not version or version != '20150315':
      raise RuntimeError('Unsupported version: {0:s}'.format(version))

    string_format = self.GetMetadataAttribute('string_format')
    if not string_format:
      string_format = 'wrc'

    if string_format not in ('pep3101', 'wrc'):
      raise RuntimeError('Unsupported string format: {0:s}'.format(
          string_format))

    self._string_format = string_format
    return True


class WinevtResourcesHelper(object):
  """Windows EventLog resources helper."""

  # LCID 0x0409 is en-US.
  DEFAULT_LCID = 0x0409

  _WINEVT_RC_DATABASE = 'winevt-rc.db'

  def __init__(self, data_location, lcid=None):
    """Initializes Windows EventLog resources helper.

    Args:
      data_location (str): data location.
      lcid (Optional[int]): Windows Language Code Identifier (LCID).
    """
    super(WinevtResourcesHelper, self).__init__()
    self._data_location = data_location
    self._lcid = lcid or self.DEFAULT_LCID
    self._windows_eventlog_providers = {}
    self._winevt_database_reader = None

  def _GetWinevtRcDatabaseReader(self):
    """Opens the Windows Event Log resource database reader.

    Returns:
      WinevtResourcesSqlite3DatabaseReader: Windows Event Log resource
          database reader or None.
    """
    if not self._winevt_database_reader and self._data_location:
      database_path = os.path.join(
          self._data_location, self._WINEVT_RC_DATABASE)
      if not os.path.isfile(database_path):
        return None

      self._winevt_database_reader = WinevtResourcesSqlite3DatabaseReader()
      if not self._winevt_database_reader.Open(database_path):
        self._winevt_database_reader = None

    return self._winevt_database_reader

  def GetMessageString(self, log_source, message_identifier):
    """Retrieves a specific Windows EventLog message string.

    Args:
      log_source (str): EventLog source, such as "Application Error".
      message_identifier (int): message identifier.

    Returns:
      str: message string or None if not available.
    """
    database_reader = self._GetWinevtRcDatabaseReader()
    if not database_reader:
      return None

    if self._lcid != self.DEFAULT_LCID:
      message_string = database_reader.GetMessage(
          log_source, self._lcid, message_identifier)
      if message_string:
        return message_string

    return database_reader.GetMessage(
        log_source, self.DEFAULT_LCID, message_identifier)