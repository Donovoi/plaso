#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Tests for Santa log parser."""

import unittest

from plaso.parsers import santa

from tests.parsers import test_lib


class SantaUnitTest(test_lib.ParserTestCase):
  """Tests for Santa log parser."""

  def testParse(self):
    """Tests the Parse function."""
    parser = santa.SantaParser()
    storage_writer = self._ParseFile(['santa.log'], parser)

    # Test file contains 194 lines
    # - 3 lines should be skipped in the results.
    # - 17 new events should be added from existing lines.

    self.assertEqual(storage_writer.number_of_warnings, 0)
    self.assertEqual(storage_writer.number_of_events, 208)

    # The order in which parser generates events is nondeterministic hence
    # we sort the events.
    events = list(storage_writer.GetSortedEvents())

    # Execution event with quarantine url.
    expected_quarantine_url = (
        'https://endpoint920510.azureedge.net/s4l/s4l/download/mac/'
        'Skype-8.28.0.41.dmg')

    expected_event_values = {
        'quarantine_url': expected_quarantine_url,
        'timestamp': '2018-08-19 03:17:55.765000'}

    self.CheckEventValues(storage_writer, events[46], expected_event_values)

    expected_message = (
        'Santa ALLOW process: /Applications/Skype.app/Contents/MacOS/Skype hash'
        ': 78b43a13b5b608fe1a5a590f5f3ff112ff16ece7befc29fc84347125f6b9ca78')
    expected_short_message = (
        'ALLOW process: /Applications/Skype.app/Contents/MacOS/Skype')

    event_data = self._GetEventDataOfEvent(storage_writer, events[46])
    self._TestGetMessageStrings(
        event_data, expected_message, expected_short_message)

    # File operation event log
    expected_event_values = {
        'action': 'WRITE',
        'file_path': '/Users/qwerty/newfile',
        'gid': '20',
        'group': 'staff',
        'pid': '303',
        'ppid': '1',
        'process': 'Finder',
        'process_path': (
            '/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder'),
        'timestamp': '2018-08-19 04:02:47.911000',
        'uid': '501',
        'user': 'qwerty'}

    self.CheckEventValues(storage_writer, events[159], expected_event_values)

    # Test common fields in file operation event.

    expected_message = (
        'Santa WRITE event /Users/qwerty/newfile by process: '
        '/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder')
    expected_short_message = 'File WRITE on: /Users/qwerty/newfile'

    event_data = self._GetEventDataOfEvent(storage_writer, events[159])
    self._TestGetMessageStrings(
        event_data, expected_message, expected_short_message)

    # Test a Disk mounts event.
    expected_event_values = {
        'action': 'DISKAPPEAR',
        'appearance': '2018-08-19T03:17:28.982Z',
        'bsd_name': 'disk2s1',
        'bus': 'Virtual Interface',
        'dmg_path': '/Users/qwerty/Downloads/Skype-8.28.0.41.dmg',
        'fs': 'hfs',
        'model': 'Apple Disk Image',
        'mount': '',
        'serial': '',
        'timestamp': '2018-08-19 03:17:29.036000',
        'volume': 'Skype'}

    self.CheckEventValues(storage_writer, events[38], expected_event_values)

    expected_message = (
        'Santa DISKAPPEAR for (/Users/qwerty/Downloads/Skype-8.28.0.41.dmg)')
    expected_short_message = 'DISKAPPEAR Skype'

    event_data = self._GetEventDataOfEvent(storage_writer, events[38])
    self._TestGetMessageStrings(
        event_data, expected_message, expected_short_message)

    # Test Disk event created from appearance timestamp.
    expected_event_values = {
        'timestamp': '2018-08-19 03:17:28.982000',
        'timestamp_desc': 'First Connection Time'}

    self.CheckEventValues(storage_writer, events[35], expected_event_values)


if __name__ == '__main__':
  unittest.main()
