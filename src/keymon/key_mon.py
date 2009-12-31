#!/usr/bin/python
#
# Copyright 2009 Scott Kirkwood. All Rights Reserved.

"""Keyboard Status Monitor.
Monitors one or more keyboards and mouses.
Shows their status graphically.
"""

__author__ = 'Scott Kirkwood (scott+keymon@forusers.com)'
__version__ = '0.14.1'

import logging
import pygtk
pygtk.require('2.0')
import gobject
import gtk
import os
import sys

import config
import evdev
import lazy_pixbuf_creator
import mod_mapper
import two_state_image
try:
  import dbus
except:
  print "Unable to import dbus interface, quitting"
  sys.exit(-1)

from ConfigParser import SafeConfigParser

from devices import InputFinder

def FixSvgKeyClosure(fname, from_tos):
  """Create a closure to modify the key.
  Args:
    from_tos: list of from, to pairs for search replace.
  Returns:
    A bound function which returns the file fname with modifications.
  """

  def FixSvgKey():
    """Given an SVG file return the SVG text fixed."""
    logging.debug('Read file %r' % fname)
    f = open(fname)
    bytes = f.read()
    f.close()
    for f, t in from_tos:
      if t == '<':
        t = '&lt;'
      elif t == '>':
        t = '&gt;'
      elif t == '&':
        t = '&amp;'
      bytes = bytes.replace(f, t)
    return bytes

  return FixSvgKey

class KeyMon:
  def __init__(self, options):
    """Create the Key Mon window.
    Options dict:
      scale: float 1.0 is default which means normal size.
      meta: boolean show the meta (windows key)
      kbd_file: string Use the kbd file given.
      emulate_middle: Emulate the middle mouse button.
      theme: Name of the theme to use to draw keys
    """
    self.options = options
    self.pathname = os.path.dirname(__file__)
    self.scale = config.get("ui", "scale", float)
    if self.scale < 1.0:
      self.svg_size = '-small'
    else:
      self.svg_size = ''
    self.enabled = {
        'MOUSE': config.get("buttons", "mouse", bool),
        'SHIFT': config.get("buttons", "shift", bool),
        'CTRL': config.get("buttons", "ctrl", bool),
        'META': config.get("buttons", "meta", bool),
        'ALT': config.get("buttons", "alt", bool),
    }
    self.emulate_middle = config.get("devices", "emulate_middle", bool)
    self.modmap = mod_mapper.SafelyReadModMap(config.get("devices", "map"))
    self.swap_buttons = config.get("devices", "swap_buttons", bool)

    if options.screenshot:
      self.finder = None
    else:
      self.finder = InputFinder()
      self.finder.connect("keyboard-found", self.DeviceFound)
      self.finder.connect("keyboard-lost", self.DeviceLost)
      self.finder.connect("mouse-found", self.DeviceFound)
      self.finder.connect("mouse-lost", self.DeviceLost)

    self.name_fnames = self.CreateNamesToFnames()
    self.pixbufs = lazy_pixbuf_creator.LazyPixbufCreator(self.name_fnames,
                                                         self.scale)
    self.CreateWindow()

  def DoScreenshot(self):
    for key in self.options.screenshot.split(','):
      try:
        event = evdev.Event(type='EV_KEY', code=key, value=1)
        self.HandleEvent(event)
      except Exception, e:
        print e
    while gtk.events_pending():
      gtk.main_iteration(False)
    win = self.window
    x, y = win.get_position()
    w, h = win.get_size()
    screenshot = gtk.gdk.Pixbuf.get_from_drawable(
        gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, True, 8, w, h),
        gtk.gdk.get_default_root_window(),
        gtk.gdk.colormap_get_system(),
        x, y, 0, 0, w, h)
    fname = 'screenshot.png'
    screenshot.save(fname, 'png')
    print 'Saved screenshot %r' % fname
    self.Destroy(None)

  def DeviceFound(self, finder, device):
    dev = evdev.Device(device.block)
    self.devices.devices.append(dev)
    self.devices.fds.append(dev.fd)

  def DeviceLost(self, finder, device):
    dev = None
    for x in self.devices.devices:
      if x.filename == device.block:
        dev = x
        break

    if dev:
      self.devices.fds.remove(dev.fd)
      self.devices.devices.remove(dev)

  def CreateNamesToFnames(self):
    ftn = {
      'MOUSE': [self.SvgFname('mouse'),],
      'BTN_MIDDLE': [self.SvgFname('mouse'), self.SvgFname('middle-mouse')],
      'SCROLL_UP': [self.SvgFname('mouse'), self.SvgFname('scroll-up-mouse')],
      'SCROLL_DOWN': [self.SvgFname('mouse'), self.SvgFname('scroll-dn-mouse')],

      'SHIFT': [self.SvgFname('shift')],
      'SHIFT_EMPTY': [self.SvgFname('shift'), self.SvgFname('whiteout-72')],
      'CTRL': [self.SvgFname('ctrl')],
      'CTRL_EMPTY': [self.SvgFname('ctrl'), self.SvgFname('whiteout-58')],
      'META': [self.SvgFname('meta'), self.SvgFname('meta')],
      'META_EMPTY': [self.SvgFname('meta'), self.SvgFname('whiteout-58')],
      'ALT': [self.SvgFname('alt')],
      'ALT_EMPTY': [self.SvgFname('alt'), self.SvgFname('whiteout-58')],
      'KEY_EMPTY': [
          FixSvgKeyClosure(self.SvgFname('one-char-template'), [('&amp;', '')]),
              self.SvgFname('whiteout-48')],
    }
    if self.swap_buttons:
      ftn.update({
        'BTN_RIGHT': [self.SvgFname('mouse'), self.SvgFname('left-mouse')],
        'BTN_LEFT': [self.SvgFname('mouse'), self.SvgFname('right-mouse')],
      })
    else:
      ftn.update({
        'BTN_LEFT': [self.SvgFname('mouse'), self.SvgFname('left-mouse')],
        'BTN_RIGHT': [self.SvgFname('mouse'), self.SvgFname('right-mouse')],
      })

    if self.scale >= 1.0:
      ftn.update({
        'KEY_SPACE': [
            FixSvgKeyClosure(self.SvgFname('two-line-wide'), [('TOP', 'Space'), ('BOTTOM', '')])],
        'KEY_TAB': [
            FixSvgKeyClosure(self.SvgFname('two-line-wide'), [('TOP', 'Tab'), ('BOTTOM', u'\u21B9')])],
        'KEY_BACKSPACE': [
            FixSvgKeyClosure(self.SvgFname('two-line-wide'), [('TOP', 'Back'), ('BOTTOM', u'\u21fd')])],
        'KEY_RETURN': [
            FixSvgKeyClosure(self.SvgFname('two-line-wide'), [('TOP', 'Enter'), ('BOTTOM', u'\u23CE')])],
        'KEY_CAPS_LOCK': [
            FixSvgKeyClosure(self.SvgFname('two-line-wide'), [('TOP', 'Capslock'), ('BOTTOM', '')])],
      })
    else:
      ftn.update({
        'KEY_SPACE': [
            FixSvgKeyClosure(self.SvgFname('one-line-wide'), [('&amp;', 'Space')])],
        'KEY_TAB': [
            FixSvgKeyClosure(self.SvgFname('one-line-wide'), [('&amp;', 'Tab')])],
        'KEY_BACKSPACE': [
            FixSvgKeyClosure(self.SvgFname('one-line-wide'), [('&amp;', 'Back')])],
        'KEY_RETURN': [
            FixSvgKeyClosure(self.SvgFname('one-line-wide'), [('&amp;', 'Enter')])],
        'KEY_CAPS_LOCK': [
            FixSvgKeyClosure(self.SvgFname('one-line-wide'), [('&amp;', 'Capslck')])],
      })
    return ftn

  def CreateWindow(self):
    self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)

    self.window.set_title('Keyboard Status Monitor')
    width, height = 30 * self.scale, 48 * self.scale
    self.window.set_default_size(int(width), int(height))
    self.window.set_decorated(False)
    #self.window.set_opacity(1.0)
    self.window.set_keep_above(True)

    self.event_box = gtk.EventBox()
    screen = self.event_box.get_screen()
    colormap = screen.get_rgba_colormap()
    self.event_box.set_colormap(colormap)

    self.window.add(self.event_box)
    self.event_box.show()

    self.hbox = gtk.HBox(False, 0)
    self.event_box.add(self.hbox)

    self.mouse_image = two_state_image.TwoStateImage(self.pixbufs, 'MOUSE')
    if not self.enabled['MOUSE']:
      self.mouse_image.hide()
    self.hbox.pack_start(self.mouse_image, False, False, 0)
    if not self.enabled['MOUSE']:
      self.mouse_image.hide()

    self.shift_image = two_state_image.TwoStateImage(
        self.pixbufs, 'SHIFT_EMPTY', self.enabled['SHIFT'])
    if not self.enabled['SHIFT']:
      self.shift_image.hide()
    self.hbox.pack_start(self.shift_image, False, False, 0)

    self.ctrl_image = two_state_image.TwoStateImage(
        self.pixbufs, 'CTRL_EMPTY')
    if not self.enabled['CTRL']:
      self.ctrl_image.hide()
    self.hbox.pack_start(self.ctrl_image, False, False, 0)

    self.meta_image = two_state_image.TwoStateImage(
        self.pixbufs, 'META_EMPTY', self.enabled['META'])
    if not self.enabled['META']:
      self.meta_image.hide()
    self.hbox.pack_start(self.meta_image, False, False, 0)

    self.alt_image = two_state_image.TwoStateImage(
        self.pixbufs, 'ALT_EMPTY', self.enabled['ALT'])
    if not self.enabled['ALT']:
      self.alt_image.hide()
    self.hbox.pack_start(self.alt_image, False, False, 0)

    self.key_image = two_state_image.TwoStateImage(self.pixbufs, 'KEY_EMPTY')
    self.key_image.timeout_secs = 0.5
    self.hbox.pack_start(self.key_image, True, True, 0)

    self.buttons = [self.mouse_image, self.shift_image, self.ctrl_image,
        self.meta_image, self.alt_image, self.key_image]

    self.hbox.show()
    self.AddEvents()

    self.window.set_decorated(config.get("ui", "decorated", bool))
    self.window.show()

  def SvgFname(self, fname):
    fullname = os.path.join(self.pathname, 'themes/%s/%s%s.svg' % (
        config.get("ui", "theme"), fname, self.svg_size))
    if self.svg_size and not os.path.exists(fullname):
      # Small not found, defaulting to large size
      fullname = os.path.join(self.pathname, 'themes/%s/%s.svg' %
                              (config.get("ui", "theme"), fname))
    return fullname

  def AddEvents(self):
    self.window.connect('destroy', self.Destroy)
    self.window.connect('button-press-event', self.ButtonPressed)
    self.event_box.connect('button_release_event', self.RightClickHandler)

    accelgroup = gtk.AccelGroup()
    key, modifier = gtk.accelerator_parse('<Control>q')
    accelgroup.connect_group(key, modifier, gtk.ACCEL_VISIBLE, self.Quit)
    self.window.add_accel_group(accelgroup)

    if self.options.screenshot:
      gobject.timeout_add(300, self.DoScreenshot)
      return

    gobject.idle_add(self.OnIdle)
    try:
      nodes = [x.block for x in self.finder.keyboards.values()] + \
              [x.block for x in self.finder.mice.values()]
      self.devices = evdev.DeviceGroup(nodes)
    except OSError, e:
      logging.exception(e)
      if str(e) == 'Permission denied':
        gksudo()
      print
      print 'You may need to run this as %r' % 'sudo %s' % sys.argv[0]
      sys.exit(-1)

  def ButtonPressed(self, widget, evt):
    if evt.button != 1:
      return True
    widget.begin_move_drag(evt.button, int(evt.x_root), int(evt.y_root), evt.time)
    return True

  def OnIdle(self):
    event = self.devices.next_event()
    self.HandleEvent(event)
    return True  # continue calling

  def HandleEvent(self, event):
    if not event:
      for button in self.buttons:
        button.EmptyEvent()
      return
    if event.type == "EV_KEY" and event.value in (0, 1):
      if type(event.code) == str:
        if event.code.startswith("KEY"):
          code_num = event.codeMaps[event.type].toNumber(event.code)
          self.HandleKey(code_num, event.value)
        elif event.code.startswith("BTN"):
          self.HandleMouseButton(event.code, event.value)
    elif event.type.startswith("EV_REL") and event.code == 'REL_WHEEL':
      self.HandleMouseScroll(event.value, event.value)

  def _HandleEvent(self, image, name, code):
    if code == 1:
      logging.debug('Switch to %s, code %s' % (name, code))
      image.SwitchTo(name)
    else:
      image.SwitchToDefault()

  def HandleKey(self, scan_code, value):
    if scan_code in self.modmap:
      code, medium_name, short_name = self.modmap[scan_code]
    else:
      print 'No mapping for scan_code %d' % scan_code
      return
    if self.scale < 1.0 and short_name:
      medium_name = short_name
    logging.debug('Key %s pressed = %r' % (code, medium_name))
    if code in self.name_fnames:
      self._HandleEvent(self.key_image, code, value)
      return
    if code.startswith('KEY_SHIFT'):
      if self.enabled['SHIFT']:
        self._HandleEvent(self.shift_image, 'SHIFT', value)
      return
    if code.startswith('KEY_ALT') or code == 'KEY_ISO_LEVEL3_SHIFT':
      if self.enabled['ALT']:
        self._HandleEvent(self.alt_image, 'ALT', value)
      return
    if code.startswith('KEY_CONTROL'):
      if self.enabled['CTRL']:
        self._HandleEvent(self.ctrl_image, 'CTRL', value)
      return
    if code.startswith('KEY_SUPER') or code == 'KEY_MULTI_KEY':
      if self.enabled['META']:
        self._HandleEvent(self.meta_image, 'META', value)
      return
    if code.startswith('KEY_KP'):
      letter = medium_name
      if code not in self.name_fnames:
        template = 'one-char-numpad-template'
        self.name_fnames[code] = [
            FixSvgKeyClosure(self.SvgFname(template), [('&amp;', letter)])]
      self._HandleEvent(self.key_image, code, value)
      return
    if code.startswith('KEY_'):
      letter = medium_name
      if code not in self.name_fnames:
        logging.debug('code not in %s' % code)
        if len(letter) == 1:
          template = 'one-char-template'
        else:
          template = 'multi-char-template'
        self.name_fnames[code] = [
            FixSvgKeyClosure(self.SvgFname(template), [('&amp;', letter)])]
      else:
        logging.debug('code in %s' % code)
      self._HandleEvent(self.key_image, code, value)
      return

  def HandleMouseButton(self, code, value):
    if self.enabled['MOUSE']:
      if self.emulate_middle and ((self.mouse_image.current == 'BTN_LEFT' and code == 'BTN_RIGHT') or
         (self.mouse_image.current == 'BTN_RIGHT' and code == 'BTN_LEFT')):
        code = 'BTN_MIDDLE'
      self._HandleEvent(self.mouse_image, code, value)
    return True

  def HandleMouseScroll(self, dir, value):
    if dir > 0:
      self._HandleEvent(self.mouse_image, 'SCROLL_UP', 1)
    elif dir < 0:
      self._HandleEvent(self.mouse_image, 'SCROLL_DOWN', 1)
    self.mouse_image.SwitchToDefault()
    return True

  def Quit(self, *args):
    self.Destroy(None)

  def Destroy(self, widget, data=None):
    config.cleanup()
    gtk.main_quit()

  def RightClickHandler(self, widget, event):
    if event.button != 3:
      return

    menu = self.CreateContextMenu()

    menu.show()
    menu.popup(None, None, None, event.button, event.time)

  def CreateContextMenu(self):
    menu = gtk.Menu()

    toggle_chrome = gtk.CheckMenuItem('Window _Chrome')
    toggle_chrome.set_active(self.window.get_decorated())
    toggle_chrome.connect_object('activate', self.ToggleChrome,
       self.window.get_decorated())
    toggle_chrome.show()
    menu.append(toggle_chrome)

    toggle_mouse = gtk.CheckMenuItem('Mouse')
    visible = self.mouse_image.flags() & gtk.VISIBLE
    toggle_mouse.set_active(visible)
    toggle_mouse.connect_object('activate', self.ToggleMouse,
        visible)
    toggle_mouse.show()
    menu.append(toggle_mouse)

    toggle_metakey = gtk.CheckMenuItem('Meta Key')
    visible = self.meta_image.flags() & gtk.VISIBLE
    toggle_metakey.set_active(visible)
    toggle_metakey.connect_object('activate', self.ToggleMetaKey,
        visible)
    toggle_metakey.show()
    menu.append(toggle_metakey)

    quit = gtk.MenuItem('_Quit\tCtrl-Q')
    quit.connect_object('activate', self.Destroy, None)
    quit.show()

    menu.append(quit)
    return menu

  def ToggleChrome(self, current):
    self.window.set_decorated(not current)
    config.set("ui", "decorated", not current)

  def ToggleMetaKey(self, current):
    self._ToggleAKey(self.meta_image, 'META', current)
    config.set("buttons", "meta", not current)

  def ToggleMouse(self, current):
    self._ToggleAKey(self.mouse_image, 'MOUSE', current)
    config.set("buttons", "mouse", not current)

  def _ToggleAKey(self, image, name, current):
    if current:
      image.showit = False
      self.enabled[name] = False
      image.hide()
    else:
      image.showit = True
      self.enabled[name] = True
      image.SwitchToDefault()

  def GetKeyboardDevices(self, bus, hal):
    self.keyboard_devices = hal.FindDeviceByCapability("input.keyboard")
    if not self.keyboard_devices:
      print "No keyboard devices found"
      sys.exit(-1)

    self.keyboard_filenames = []
    for keyboard_device in self.keyboard_devices:
      dev_obj = bus.get_object ("org.freedesktop.Hal", keyboard_device)
      dev = dbus.Interface (dev_obj, "org.freedesktop.Hal.Device")
      self.keyboard_filenames.append(dev.GetProperty("input.device"))

  def GetMouseDevices(self, bus, hal):
    self.mouse_devices = hal.FindDeviceByCapability ("input.mouse")
    if not self.mouse_devices:
      print "No mouse devices found"
      sys.exit(-1)
    self.mouse_filenames = []
    for mouse_device in self.mouse_devices:
      dev_obj = bus.get_object ("org.freedesktop.Hal", mouse_device)
      dev = dbus.Interface (dev_obj, "org.freedesktop.Hal.Device")
      self.mouse_filenames.append(dev.GetProperty("input.device"))

def ShowVersion():
  print 'Keymon version %s.' % __version__
  print 'Written by %s' % __author__

def Main():
  import optparse
  parser = optparse.OptionParser()
  parser.add_option('-s', '--smaller', dest='smaller', default=False, action='store_true',
                    help='Make the dialog 25% smaller than normal.')
  parser.add_option('-l', '--larger', dest='larger', default=False, action='store_true',
                    help='Make the dialog 25% larger than normal.')
  parser.add_option('-m', '--meta', dest='meta', action='store_true',
                    help='Show the meta (windows) key.')
  parser.add_option('--nomouse', dest='nomouse', action='store_true',
                    help='Hide the mouse.')
  parser.add_option('--noshift', dest='noshift', action='store_true',
                    help='Hide the shift key.')
  parser.add_option('--noctrl', dest='noctrl', action='store_true',
                    help='Hide the ctrl key.')
  parser.add_option('--noalt', dest='noalt', action='store_true',
                    help='Hide the alt key.')
  parser.add_option('--scale', dest='scale', default=config.get("ui", "scale"),
                    type='float',
                    help='Scale the dialog. ex. 2.0 is 2 times larger, 0.5 is half the size.')
  parser.add_option('--kbdfile', dest='kbd_file',
                    default=config.get("devices", "map"),
                    help='Use this kbd filename instead running xmodmap.')
  parser.add_option('--swap', dest='swap_buttons', action='store_true',
                    help='Swap the mouse buttons.')
  parser.add_option('--emulate-middle', dest='emulate_middle', action="store_true",
                    help=('When you press the left, and right mouse buttons at the same time, '
                          'it displays as a middle mouse button click. '))
  parser.add_option('-v', '--version', dest='version', action='store_true',
                    help='Show version information and exit.')
  parser.add_option('-t', '--theme', dest='theme',
                    default=config.get("ui", "theme"),
                    help='The theme to use when drawing status images (ex. "-t apple").')
  parser.add_option('--list-themes', dest='list_themes', action='store_true',
                    help='List available themes')

  group = optparse.OptionGroup(parser, 'Developer Options',
                    'These options are for developers.')
  group.add_option('-d', '--debug', dest='debug', action='store_true',
                    help='Output debugging information.')
  group.add_option('--screenshot', dest='screenshot',
                    help='Create a "screenshot.png" and exit. '
                    'Pass a comma separated list of keys to simulate (ex. "KEY_A,KEY_LEFTCTRL").')
  parser.add_option_group(group)
  
  (options, args) = parser.parse_args()
  
  if options.version:
    ShowVersion()
    sys.exit(-1)
  if options.debug:
    logging.basicConfig(level=logging.DEBUG, format = "%(filename)s [%(lineno)d]: %(levelname)s %(message)s")
  if options.smaller:
    options.scale = 0.75
  elif options.larger:
    options.scale = 1.25
  if options.list_themes:
    print "Available themes:"
    for entry in sorted(os.listdir("themes")):
        try:
            parser = SafeConfigParser()
            parser.read(os.path.join("themes", entry, "config"))
            desc = parser.get("theme", "description")
            print "%s: %s" % (entry, desc)
        except:
            pass
    raise SystemExit()
  
  config.set("ui", "scale", options.scale)
  config.set("ui", "theme", options.theme)
  
  if options.nomouse:
    config.set("buttons", "mouse", not options.nomouse)
  if options.noshift:
    config.set("buttons", "shift", not options.noshift)
  if options.noctrl:
    config.set("buttons", "ctrl", not options.noctrl)
  if options.noalt:
    config.set("buttons", "alt", not options.noalt)
  if options.meta:
    config.set("buttons", "meta", options.meta)
    
  config.set("devices", "map", options.kbd_file)
  config.set("devices", "emulate_middle", bool(options.emulate_middle))
  config.set("devices", "swap_buttons", bool(options.swap_buttons))
  
  keymon = KeyMon(options)
  gtk.main()

if __name__ == "__main__":
  Main()