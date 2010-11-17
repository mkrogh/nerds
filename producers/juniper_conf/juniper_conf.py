#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2010, NORDUnet A/S.
#
# This file is part of the NERDS producer juniper_conf.py.
#
# NORDUbot is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# NORDUbot is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with NERDS. If not, see <http://www.gnu.org/licenses/>.

from xml.dom import minidom
import os
import sys
import json
import ConfigParser
import argparse

'''
Depends on pexpect for remote config gathering.
If you have Python <2.7 you need to install argparse manually.
'''

class Router:
    def __init__(self):
        self.name = ''
        self.interfaces = []
        self.bgp_peerings = []

    def to_json(self):
        j = {'name':self.name}
        interfaces = []
        for interface in self.interfaces:
            interfaces.append(interface.to_json())
        j['interfaces'] = interfaces
        bgp_peerings = []
        for peering in self.bgp_peerings:
            bgp_peerings.append(peering.to_json())
        j['bgp_peerings'] = bgp_peerings
        return j

class Interface:
    def __init__(self):
        self.name = ''
        self.bundle = ''
        self.description = ''
        self.vlantagging = ''
        self.tunneldict = []
        # Unit dict is a list of dictionaries containing units to
        # interfaces, should be index like {'unit': 'name',
        # 'desc': 'foo', 'vlanid': 'bar', 'address': 'xyz'}
        self.unitdict = []

    def to_json(self):
        j = {'name':self.name, 'bundle':self.bundle,
            'description':self.description,
            'vlantagging':self.vlantagging, 'tunnels':self.tunneldict,
            'units':self.unitdict}
        return j

class BgpPeering:
    def __init__(self):
        self.type = None
        self.remote_address = None
        self.description = None
        self.local_address = None
        self.group = None
        self.as_number = None

    def to_json(self):
        j = {'type':self.type,'remote_address':self.remote_address,
            'description':self.description, 'local_address':self.local_address,
            'group':self.group,'as_number':self.as_number}
        return j


def get_firstchild(element, tag):
    '''
    Takes xml element and a name of a tag.
    Returns the data from a tag when looping over a parent.
    '''
    try:
        data = element.getElementsByTagName(tag).item(0).firstChild.data
    except AttributeError:
        data = None
    return data

def get_hostname(xmldoc):
    '''
    Finds and returns the hostname from a JunOS config.
    '''
    re = xmldoc.getElementsByTagName('host-name')
    domain = xmldoc.getElementsByTagName('domain-name')

    try:
        hostname = '%s.%s' % (re[0].firstChild.data,
                            domain[0].firstChild.data)
    except AttributeError:
        print 'No host-name element in config file, check the config.'
        sys.exit(1)

    if 're0' in hostname or 're1' in hostname:
        hostname = hostname.replace('-re0','').replace('-re1','')

    return hostname

def get_interfaces(xmldoc):
    '''
    Returns a list of Interface objects made out from all interfaces in
    the JunOS config.

    Dive in to Python writes:
    "When you parse an XML document, you get a bunch of Python objects
    that represent all the pieces of the XML document, and some of these
    Python objects represent attributes of the XML elements. But the
    (Python) objects that represent the (XML) attributes also have
    (Python) attributes, which are used to access various parts of the
    (XML) attribute that the object represents." ARGH ;)
    '''

    interfaces = xmldoc.getElementsByTagName('interfaces')
    listofinterfaces = []

    for i in interfaces:
        interface = list(i.getElementsByTagName('interface'))

    for elements in interface:
        tempInterface = Interface()

        # Interface name, ge-0/1/0 or similar
        tempInterface.name = get_firstchild(elements, 'name')

        # Is the interface vlan-tagging?
        vlantag = elements.getElementsByTagName('vlan-tagging').item(0)
        if vlantag != None:
            tempInterface.vlantagging = True
        else:
            tempInterface.vlantagging = False

        # Is it a bundled interface?
        tempInterface.bundle = get_firstchild(elements, 'bundle')

        # Get the interface description
        tempInterface.desc = get_firstchild(elements, 'description')

        # Get tunnel information if any
        source = get_firstchild(elements, 'source')
        destination = get_firstchild(elements, 'destination')
        tempInterface.tunneldict.append({'source' : source,
            'destination': destination})

        # Get all information per interface unit
        units = elements.getElementsByTagName('unit')
        unitemp = ''
        desctemp = ''
        vlanidtemp = ''
        nametemp = ''
        for unit in units:
            unittemp = get_firstchild(unit, 'name')
            desctemp = get_firstchild(unit, 'description')
            vlanidtemp = get_firstchild(unit, 'vlan-id')
            addresses = unit.getElementsByTagName('address')
            nametemp = []
            for address in addresses:
                nametemp.append(get_firstchild(address, 'name'))

            tempInterface.unitdict.append({'unit': unittemp,
                'description': desctemp, 'vlanid': vlanidtemp,
                'address': nametemp})

        # Add interface to the collection of interfaces
        listofinterfaces.append(tempInterface)

    return listofinterfaces

def get_bgp_peerings(xmldoc):
    '''
    Returns a list of all BGP peerings in the JunOS configuration.
    '''
    bgp = xmldoc.getElementsByTagName('bgp')
    groups = bgp[0].getElementsByTagName('group')
    list_of_peerings = []

    for element in groups:
        group_name = get_firstchild(element, 'name')
        group_type = get_firstchild(element, 'type')
        # Seems like only internal BGP peerings have local-address
        # set. Need to find a good way to get it for external
        # peerings as well. Erik talked about matching sub nets.
        local_address = get_firstchild(element, 'local-address')

        neighbors = element.getElementsByTagName('neighbor')
        for neighbor in neighbors:
            #if not neighbor.hasAttribute('inactive')
            peering = BgpPeering()
            peering.type = group_type
            peering.remote_address = get_firstchild(neighbor, 'name')
            peering.description = get_firstchild(neighbor,
                'description')
            peering.local_address = local_address
            peering.group = group_name
            peering.as_number = get_firstchild(neighbor,'peer-as')
            list_of_peerings.append(peering)

    return list_of_peerings


def parse_router(xmldoc):
    '''
    Takes a JunOS conf in XML format and returns a Router object.
    '''
    router = Router()
    router.name = get_hostname(xmldoc)
    router.interfaces = get_interfaces(xmldoc)
    router.bgp_peerings = get_bgp_peerings(xmldoc)

    return router

def init_config(path):
    '''
    Initializes the configuration file located in the path provided.
    '''
    try:
       config = ConfigParser.SafeConfigParser()
       config.read(path)
       return config
    except IOError as (errno, strerror):
        print "I/O error({0}): {1}".format(errno, strerror)

def get_local_xml(f):
    '''
    Parses the provided file to an XML document and returns it.

    Returns False if the XML is malformed.
    '''
    try:
        xmldoc = minidom.parse(f)
    except ExpatError:
        print 'Malformed XML input from %s.' % host
        return False

    return xmldoc

def get_remote_xml(host, username, password):
    '''
    Tries to ssh to the supplied JunOS machine and execute the command
    to show current configuration i XML format.

    Returns False if the configuration could not be retrived.
    '''
    try:
        import pexpect
    except ImportError:
        print 'Install module pexpect to be able to use remote sources.'
        return False

    ssh_newkey = 'Are you sure you want to continue connecting'
    login_choices = [ssh_newkey, 'Password:', 'password:', pexpect.EOF]

    try:
        s = pexpect.spawn('ssh %s@%s' % (username,host))
        print 'Trying to connect to %s@%s...' % (username, host)
        i = s.expect(login_choices)
        if i == 0:
            print "Storing SSH key."
            s.sendline('yes')
            i = s.expect(login_choices)
        if i == 1 or i == 2:
            s.sendline(password)
            print 'Connected to %s.' % host
        elif i == 3:
            print "I either got key problems or connection timeout."
            return False
        s.expect('>', timeout=60)
        # Send JunOS command for displaying the configuration in XML
        # format.
        s.sendline ('show configuration | display xml | no-more')
        s.expect('</rpc-reply>', timeout=120)   # expect end of the XML
                                                # blob
        xml = s.before # take everything printed before last expect()
        s.sendline('exit')
    except pexpect.ExceptionPexpect:
        print 'Timed out in %s.' % host
        return False

    xml += '</rpc-reply>' # Add the end element as pexpect steals it
    # Remove the first line in the output which is the command sent
    # to JunOS.
    xml = xml.lstrip('show configuration | display xml | no-more')
    try:
        xmldoc = minidom.parseString(xml)
    except ExpatError:
        print 'Malformed XML input from %s.' % host
        return False

    return xmldoc

def main():

    # User friendly usage output
    parser = argparse.ArgumentParser()
    parser.add_argument('-C', nargs='?',
        help='Path to the configuration file.')
    parser.add_argument('-O', nargs='?',
        help='Path to output directory.')
    parser.add_argument('-N', action='store_true',
        help='Don\'t write output to disk.')
    args = parser.parse_args()

    # Load the configuration file
    if args.C == None:
        print 'Please provide a configuration file with -C.'
        sys.exit(1)
    else:
        config = init_config(args.C)

    # List to collect configuration in XML document format for parsing
    xmldocs = []

    # Process local files
    local_sources = config.get('sources', 'local').split()
    for f in local_sources:
        xmldoc = get_local_xml(f)
        if xmldoc:
            xmldocs.append(xmldoc)

    # Process remote hosts
    remote_sources = config.get('sources', 'remote').split()
    for host in remote_sources:
        xmldoc = get_remote_xml(host, config.get('ssh', 'user'),
            config.get('ssh', 'password'))
        if xmldoc:
            xmldocs.append(xmldoc)

    # Parse the xml documents to create Router objects
    parsed_conf_xml = []
    for doc in xmldocs:
        parsed_conf_xml.append(parse_router(doc))

    # Call .tojson() for all Router objects and merge that with the
    # nerds template. Store the json in the dictionary out with the key
    # name.
    out = {}
    for c in parsed_conf_xml:
        template = {'host':{'name': c.name, 'version': 1,
            'juniper_conf': {}}}
        template['host']['juniper_conf'] = c.to_json()
        out[c.name] = json.dumps(template, indent=4)

    # Output directory should be ./json/ if nothing else is specified
    out_dir = './json/'

    # Depending on which arguments the user provided print to file or
    # to stdout.
    if args.N is True:
        for key in out:
            print out[key]
    else:
        if args.O:
            out_dir = args.O
        # Pad with / if user provides a broken path
        if out_dir[-1] != '/':
            out_dir += '/'
        for key in out:
            try:
                try:
                    f = open('%s%s.json' % (out_dir, key), 'w')
                except IOError:
                    # The directory to write in must exist
                    os.mkdir(out_dir)
                    f = open('%s%s.json' % (out_dir, key), 'w')
                f.write(out[key])
                f.close()
            except IOError as (errno, strerror):
                print "I/O error({0}): {1}".format(errno, strerror)

    return 0

if __name__ == '__main__':
    main()

