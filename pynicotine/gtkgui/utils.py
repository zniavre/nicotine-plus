# COPYRIGHT (C) 2020 Nicotine+ Team
# COPYRIGHT (C) 2020 Lene Preuss <lene.preuss@gmail.com>
# COPYRIGHT (C) 2016-2017 Michael Labouebe <gfarmerfr@free.fr>
# COPYRIGHT (C) 2016 Mutnick <muhing@yahoo.com>
# COPYRIGHT (C) 2008-2011 Quinox <quinox@users.sf.net>
# COPYRIGHT (C) 2006-2009 Daelstorm <daelstorm@gmail.com>
# COPYRIGHT (C) 2003-2004 Hyriand <hyriand@thegraveyard.org>
#
# GNU GENERAL PUBLIC LICENSE
#    Version 3, 29 June 2007
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import re
import sys
import time
import types
import urllib.parse
import webbrowser
from gettext import gettext as _

from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import GObject as gobject
from gi.repository import Gtk as gtk
from gi.repository import Pango as pango

from pynicotine import slskmessages
from pynicotine.gtkgui.dialogs import EntryDialog
from pynicotine.gtkgui.countrycodes import code2name
from pynicotine.utils import CleanFile
from pynicotine.utils import executeCommand


DECIMALSEP = ""

URL_RE = re.compile("(\\w+\\://[^\\s]+)|(www\\.\\w+\\.\\w+.*?)|(mailto\\:[^\\s]+)")
PROTOCOL_HANDLERS = {}
CATCH_URLS = 0
HUMANIZE_URLS = 0
USERNAMEHOTSPOTS = 0
NICOTINE = None


# we could move this into a new class
previouscountrypath = None


def showCountryTooltip(widget, x, y, tooltip, sourcecolumn, stripprefix='flag_'):

    global previouscountrypath
    try:
        # the returned path of widget.get_path_at_pos is not correct since
        # this function pretends there's no header!
        # This also means we cannot look up the column for the very last user in the list
        # since the y is too big.
        # Therefore we'll use a y-value of 0 on all lookups
        (incorrectpath, column, cx, cy) = widget.get_path_at_pos(x, 0)

        # The return path of this func is okay, but it doesn't return the column -_-
        (path, droppos) = widget.get_dest_row_at_pos(x, y)
    except TypeError:
        # Either function returned None
        return False

    # If the mouse is pointing at a new path destroy the tooltip so it can be recreated next time
    if path != previouscountrypath:
        previouscountrypath = path
        return False

    title = column.get_title()

    if title != _("Country"):
        return False

    model = widget.get_model()
    iter = model.get_iter(path)
    value = model.get_value(iter, sourcecolumn)

    # Avoid throwing an error in there's no flag
    if value is None:
        return False

    if not value.startswith(stripprefix):
        tooltip.set_text(_("Unknown"))
        return True

    value = value[len(stripprefix):]
    if value:
        countryname = code2name(value)
    else:
        countryname = "Earth"

    if countryname:
        countryname = _(countryname)
    else:
        countryname = _("Unknown (%(countrycode)s)") % {'countrycode': value}

    tooltip.set_text(countryname)

    return True


def FillFileGroupingCombobox(combobox):
    grouplist = gtk.ListStore(str)
    groups = [
        "No grouping",
        "Group by folder",
        "Group by user",
    ]

    for group in groups:
        grouplist.append([group])

    combobox.set_model(grouplist)
    renderer_text = gtk.CellRendererText()
    combobox.pack_start(renderer_text, True)
    combobox.add_attribute(renderer_text, "text", 0)


def SelectUserRowIter(fmodel, sel, user_index, selected_user, iter):
    while iter is not None:
        user = fmodel.get_value(iter, user_index)

        if selected_user == user:
            sel.select_path(fmodel.get_path(iter),)

        child = fmodel.iter_children(iter)

        SelectUserRowIter(fmodel, sel, user_index, selected_user, child)

        iter = fmodel.iter_next(iter)


def CollapseTreeview(treeview, groupingmode):
    treeview.collapse_all()

    if groupingmode == 1:
        # Group by folder

        model = treeview.get_model()
        iter = model.get_iter_first()

        while iter is not None:
            path = model.get_path(iter)
            treeview.expand_to_path(path)
            iter = model.iter_next(iter)


def InitialiseColumns(treeview, *args):

    i = 0
    cols = []

    for c in args:

        if c[2] == "text":
            renderer = gtk.CellRendererText()
            renderer.set_padding(10, 3)

            column = gtk.TreeViewColumn(c[0], renderer, text=i)
        elif c[2] == "center":
            renderer = gtk.CellRendererText()
            renderer.set_property("xalign", 0.5)

            column = gtk.TreeViewColumn(c[0], renderer, text=i)
        elif c[2] == "number":
            renderer = gtk.CellRendererText()
            renderer.set_property("xalign", 0.9)

            column = gtk.TreeViewColumn(c[0], renderer, text=i)
            column.set_alignment(0.9)
        elif c[2] == "edit":
            renderer = gtk.CellRendererText()
            renderer.set_padding(10, 3)
            renderer.set_property('editable', True)
            column = gtk.TreeViewColumn(c[0], renderer, text=i)
        elif c[2] == "combo":
            renderer = gtk.CellRendererCombo()
            renderer.set_padding(10, 3)
            renderer.set_property('text-column', 0)
            renderer.set_property('editable', True)
            column = gtk.TreeViewColumn(c[0], renderer, text=i)
        elif c[2] == "progress":
            renderer = gtk.CellRendererProgress()
            column = gtk.TreeViewColumn(c[0], renderer, value=i)
        elif c[2] == "toggle":
            renderer = gtk.CellRendererToggle()
            column = gtk.TreeViewColumn(c[0], renderer, active=i)
            renderer.set_property("xalign", 0.5)
        else:
            renderer = gtk.CellRendererPixbuf()
            column = gtk.TreeViewColumn(c[0], renderer, pixbuf=i)

        if c[1] == -1:
            column.set_resizable(False)
            column.set_sizing(gtk.TreeViewColumnSizing.AUTOSIZE)
        else:
            column.set_resizable(True)
            if c[1] == 0:
                column.set_sizing(gtk.TreeViewColumnSizing.GROW_ONLY)
            else:
                column.set_sizing(gtk.TreeViewColumnSizing.FIXED)
                column.set_fixed_width(c[1])
            column.set_min_width(0)

        if len(c) > 3 and type(c[3]) is not list:
            column.set_cell_data_func(renderer, c[3])

        if len(c) > 4:
            foreground = c[4][0]
            background = c[4][1]

            if foreground == "":
                foreground = None

            if background == "":
                background = None

            renderer.set_property("foreground", foreground)
            renderer.set_property("background", background)

        column.set_reorderable(False)
        column.set_widget(gtk.Label.new(c[0]))
        column.get_widget().set_margin_start(6)
        column.get_widget().show()

        treeview.append_column(column)

        cols.append(column)

        i += 1

    return cols


def HideColumns(cols, visibility_list):
    try:
        for i in range(len(cols)):

            parent = cols[i].get_widget().get_ancestor(gtk.Button)
            if parent:
                parent.connect('button_press_event', PressHeader)

            # Read Show / Hide column settings from last session
            cols[i].set_visible(visibility_list[i])

        # Make sure the width of the last visible column isn't fixed
        for i in reversed(range(len(cols))):

            if cols[i].get_visible():
                column = cols[i]
                column.set_sizing(gtk.TreeViewColumnSizing.AUTOSIZE)
                column.set_resizable(False)
                column.set_fixed_width(-1)
                break

    except IndexError:
        # Column count in config is probably incorrect (outdated?), don't crash
        pass


def PressHeader(widget, event):
    if event.button != 3:
        return False
    columns = widget.get_parent().get_columns()
    visible_columns = [column for column in columns if column.get_visible()]
    one_visible_column = len(visible_columns) == 1
    menu = gtk.Menu()
    pos = 1
    for column in columns:
        title = column.get_title()
        if title == "":
            title = _("Column #%i") % pos
        item = gtk.CheckMenuItem(title)
        if column in visible_columns:
            item.set_active(True)
            if one_visible_column:
                item.set_sensitive(False)
        else:
            item.set_active(False)
        item.connect('activate', header_toggle, columns, pos - 1)
        menu.append(item)
        pos += 1

    menu.show_all()
    menu.attach_to_widget(widget.get_toplevel(), None)
    menu.popup(None, None, None, None, event.button, event.time)

    return True


def header_toggle(menuitem, columns, index):
    column = columns[index]
    column.set_visible(not column.get_visible())

    # Make sure the width of the last visible column isn't fixed
    for i in reversed(range(len(columns))):

        if columns[i].get_visible():
            column = columns[i]
            column.set_sizing(gtk.TreeViewColumnSizing.AUTOSIZE)
            column.set_resizable(False)
            column.set_fixed_width(-1)
            break

    """ If the column we toggled the visibility of is now the last visible one,
    the previously last visible column should've resized to fit properly now,
    since it was set to AUTOSIZE. We can now set the previous column to FIXED,
    and make it resizable again. """

    prev_column = columns[index - 1]
    prev_column.set_sizing(gtk.TreeViewColumnSizing.FIXED)
    prev_column.set_resizable(True)

    NICOTINE.SaveColumns()


def SetTreeviewSelectedRow(treeview, event):
    """Handles row selection when right-clicking in a treeview"""

    pathinfo = treeview.get_path_at_pos(event.x, event.y)
    selection = treeview.get_selection()

    if pathinfo is not None:
        path, col, cell_x, cell_y = pathinfo

        # Make sure we don't attempt to select a single row if the row is already
        # in a selection of multiple rows, otherwise the other rows will be unselected
        if selection.count_selected_rows() <= 1 or not selection.path_is_selected(path):
            treeview.grab_focus()
            treeview.set_cursor(path, col, False)
    else:
        selection.unselect_all()


def ScrollBottom(widget):
    va = widget.get_vadjustment()
    try:
        va.set_value(va.get_upper() - va.get_page_size())
    except AttributeError:
        pass
    widget.set_vadjustment(va)
    return False


def UrlEvent(tag, widget, event, iter, url):
    if tag.last_event_type == Gdk.EventType.BUTTON_PRESS and event.button.type == Gdk.EventType.BUTTON_RELEASE and event.button.button == 1:
        if url[:4] == "www.":
            url = "http://" + url
        OpenUri(url, widget.get_toplevel())
    tag.last_event_type = event.button.type


def OpenUri(uri, window):
    """Open a URI in an external (web) browser. The given argument has
    to be a properly formed URI including the scheme (fe. HTTP).
    As of now failures will be silently discarded."""

    # Situation 1, user defined a way of handling the protocol
    protocol = uri[:uri.find(":")]
    if protocol in PROTOCOL_HANDLERS:
        if isinstance(PROTOCOL_HANDLERS[protocol], types.MethodType):
            PROTOCOL_HANDLERS[protocol](uri.strip())
            return
        if PROTOCOL_HANDLERS[protocol]:
            executeCommand(PROTOCOL_HANDLERS[protocol], uri)
            return

    # Situation 2, user did not define a way of handling the protocol
    if sys.platform == "win32" and webbrowser:
        webbrowser.open(uri)
        return

    try:
        gtk.show_uri_on_window(window, uri, Gdk.CURRENT_TIME)
    except AttributeError:
        screen = window.get_screen()
        gtk.show_uri(screen, uri, Gdk.CURRENT_TIME)


def AppendLine(textview, line, tag=None, timestamp=None, showstamp=True, timestamp_format="%H:%M:%S", username=None, usertag=None, scroll=True):

    if type(line) not in (type(""), type("")):
        line = str(line)  # Error messages are sometimes tuples

    def _makeurltag(buffer, tag, url):
        props = {}

        color = NICOTINE.np.config.sections["ui"]["urlcolor"]

        if color != "":
            props["foreground"] = color

        props["underline"] = pango.Underline.SINGLE
        tag = buffer.create_tag(**props)
        tag.last_event_type = -1
        tag.connect("event", UrlEvent, url)
        return tag

    def _append(buffer, text, tag):
        iter = buffer.get_end_iter()

        if tag is not None:
            buffer.insert_with_tags(iter, text, tag)
        else:
            buffer.insert(iter, text)

    def _usertag(buffer, section):
        # Tag usernames with popup menu creating tag, and away/online/offline colors
        if USERNAMEHOTSPOTS and username is not None and usertag is not None:
            np = re.compile(re.escape(str(username)))
            match = np.search(section)
            if match is not None:
                start2 = section[:match.start()]
                name = match.group()[:]
                start = section[match.end():]
                _append(buffer, start2, tag)
                _append(buffer, name, usertag)
                _append(buffer, start, tag)
            else:
                _append(buffer, section, tag)
        else:
            _append(buffer, section, tag)

    scrolledwindow = textview.get_parent()

    try:
        va = scrolledwindow.get_vadjustment()
    except AttributeError:
        # scrolledwindow may have disappeared already while Nicotine+ was shutting down
        return

    bottom = (va.get_value() + va.get_page_size()) >= va.get_upper()

    buffer = textview.get_buffer()
    text_iter_start, text_iter_end = buffer.get_bounds()
    linenr = buffer.get_line_count()

    TIMESTAMP = None
    TS = 0

    if showstamp and NICOTINE.np.config.sections["logging"]["timestamps"]:
        if timestamp_format and not timestamp:
            TIMESTAMP = time.strftime(timestamp_format)
            line = "%s %s" % (TIMESTAMP, line)
        elif timestamp_format and timestamp:
            TIMESTAMP = time.strftime(timestamp_format, time.localtime(timestamp))
            line = "%s %s" % (TIMESTAMP, line)

    # Ensure newlines are in the correct place
    # We want them before the content, to prevent adding an empty line at the end of the TextView
    line = line.strip("\n")
    if text_iter_end.get_offset() > 0:
        line = "\n" + line

    if TIMESTAMP is not None:
        TS = len("\n") + len(TIMESTAMP)

    # Append timestamp, if one exists, cut it from remaining line (to avoid matching against username)
    _append(buffer, line[:TS], tag)
    line = line[TS:]
    # Match first url
    match = URL_RE.search(line)
    # Highlight urls, if found and tag them
    while CATCH_URLS and match:
        start = line[:match.start()]
        _usertag(buffer, start)
        url = match.group()
        urltag = _makeurltag(buffer, tag, url)
        line = line[match.end():]

        if url.startswith("slsk://") and HUMANIZE_URLS:
            url = urllib.parse.unquote(url)

        _append(buffer, url, urltag)
        # Match remaining url
        match = URL_RE.search(line)

    if line:
        _usertag(buffer, line)

    if scroll and bottom:
        GLib.idle_add(ScrollBottom, scrolledwindow)

    return linenr


class BuddiesComboBox:

    def __init__(self, frame, ComboBox):

        self.frame = frame

        self.items = {}

        self.combobox = ComboBox

        self.store = gtk.ListStore(gobject.TYPE_STRING)
        self.combobox.set_model(self.store)
        self.combobox.set_entry_text_column(0)

        self.store.set_default_sort_func(lambda *args: -1)
        self.store.set_sort_column_id(-1, gtk.SortType.ASCENDING)

        self.combobox.show()

    def Fill(self):

        self.items.clear()
        self.store.clear()

        self.items[""] = self.store.append([""])

        for user in self.frame.np.config.sections["server"]["userlist"]:
            self.items[user[0]] = self.store.append([user[0]])

        self.store.set_sort_column_id(0, gtk.SortType.ASCENDING)

    def Append(self, item):

        if item in self.items:
            return

        self.items[item] = self.combobox.get_model().append([item])

    def Remove(self, item):

        if item in self.items:
            self.combobox.get_model().remove(self.items[item])
            del self.items[item]


class ImageLabel(gtk.Box):

    def __init__(self, label="", image=None, onclose=None, closebutton=False, angle=0, show_image=True, statusimage=None, show_status_image=False):

        gtk.Box.__init__(self)

        self.closebutton = closebutton
        self.angle = angle
        self._show_image = show_image
        self._show_status_image = show_status_image
        self.notify = 0

        self._entered = 0
        self._pressed = 0

        self.onclose = onclose
        self.status_img = None
        self.statusimage = gtk.Image()
        self.label = gtk.Label()
        self.text = label

        self.set_text(self.text)

        self.label.set_angle(angle)
        self.label.show()

        if self._show_status_image:
            self.set_status_image(statusimage)
            self.statusimage.show()

        self.image = gtk.Image()
        self.set_image(image)

        if self._show_image:
            self.image.show()

        self._pack_children()
        self._order_children()

    def _pack_children(self):
        self.set_spacing(0)
        if "Box" in self.__dict__:
            for widget in self.Box.get_children():
                self.Box.remove(widget)
            self.remove(self.Box)
            self.Box.destroy()
            del self.Box

        self.Box = gtk.Box()

        if self.angle in (90, -90):
            self.Box.set_orientation(gtk.Orientation.VERTICAL)
        else:
            self.angle = 0

        self.Box.set_spacing(2)
        self.add(self.Box)
        self.Box.show()

        self.Box.pack_start(self.statusimage, False, False, 0)
        self.Box.pack_start(self.label, True, True, 0)
        self.Box.pack_start(self.image, False, False, 0)

        if self.closebutton and self.onclose is not None:
            self._add_close_button()

    def _order_children(self):

        if self.angle == 90:
            if "button" in self.__dict__ and self.closebutton != 0:
                self.Box.reorder_child(self.button, 0)
                self.Box.reorder_child(self.image, 1)
                self.Box.reorder_child(self.label, 2)
                self.Box.reorder_child(self.statusimage, 3)
            else:
                self.Box.reorder_child(self.image, 0)
                self.Box.reorder_child(self.label, 1)
                self.Box.reorder_child(self.statusimage, 2)
        else:
            self.Box.reorder_child(self.statusimage, 0)
            self.Box.reorder_child(self.label, 1)
            self.Box.reorder_child(self.image, 2)
            if "button" in self.__dict__ and self.closebutton != 0:
                self.Box.reorder_child(self.button, 3)

    def set_onclose(self, closebutton):
        self.closebutton = closebutton

        if self.closebutton:
            self._add_close_button()
        else:
            self._remove_close_button()
        self._order_children()

    def show_image(self, show=True):
        self._show_image = show

        if self._show_image:
            self.image.show()
        else:
            self.image.hide()

    def set_angle(self, angle):
        self.angle = angle
        self.label.set_angle(self.angle)
        self._remove_close_button()

        self._pack_children()
        self._order_children()

    def _add_close_button(self):
        if "button" in self.__dict__:
            return
        self.button = gtk.Button()
        img = gtk.Image()
        img.set_from_icon_name("window-close-symbolic", gtk.IconSize.MENU)
        self.button.add(img)
        if self.onclose is not None:
            self.button.connect("clicked", self.onclose)
        self.button.set_relief(gtk.ReliefStyle.NONE)

        self.button.show_all()
        self.Box.pack_start(self.button, False, False, 0)

    def _remove_close_button(self):
        if "button" not in self.__dict__:
            return
        self.Box.remove(self.button)
        self.button.destroy()
        del self.button

    def set_text_color(self, notify=None, text=None):
        if notify is None:
            notify = self.notify
        else:
            self.notify = notify

        color = NICOTINE.np.config.sections["ui"]["tab_default"]

        if NICOTINE.np.config.sections["notifications"]["notification_tab_colors"]:
            if notify == 1:
                color = NICOTINE.np.config.sections["ui"]["tab_changed"]
            elif notify == 2:
                color = NICOTINE.np.config.sections["ui"]["tab_hilite"]

        try:
            rgba = Gdk.RGBA()
            rgba.parse(color)
        except Exception:
            color = ""

        if text is not None:
            self.text = text

        if not color:
            self.label.set_text("%s" % self.text)
        else:
            self.label.set_markup("<span foreground=\"%s\">%s</span>" % (color, self.text.replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")))

    def set_image(self, img):
        self.img = img
        self.image.set_from_pixbuf(img)

    def get_image(self):
        return self.img

    def set_status_image(self, img):
        if img is self.status_img:
            return
        if NICOTINE:
            if NICOTINE.np.config.sections["ui"]["tab_status_icons"]:
                self.statusimage.show()
            else:
                self.statusimage.hide()
        self.status_img = img
        self.statusimage.set_from_pixbuf(img)

    def get_status_image(self):
        return self.status_img

    def set_text(self, lbl):
        self.set_text_color(notify=None, text=lbl)

    def get_text(self):
        return self.label.get_text()


class IconNotebook:
    """ This class implements a pseudo gtk.Notebook
    On top of what a gtk.Notebook provides:
    - You can have icons on the notebook tab.
    - You can choose the label orientation (angle).
    """

    def __init__(self, images, angle=0, tabclosers=False, show_image=True, reorderable=True, show_status_image=False, notebookraw=None):

        # We store the real gtk.Notebook object
        self.Notebook = notebookraw
        self.Notebook.set_show_border(True)

        self.tabclosers = tabclosers
        self.reorderable = reorderable

        self.images = images
        self._show_image = show_image
        self._show_status_image = show_status_image

        self.pages = []

        self.Notebook.connect("switch-page", self.dismiss_icon)
        self.Notebook.connect("key_press_event", self.OnKeyPress)

        self.angle = angle

    def set_reorderable(self, reorderable):

        self.reorderable = reorderable

        for data in self.pages:
            page, label_tab, status, label_tab_menu = data
            try:
                self.Notebook.set_tab_reorderable(page, self.reorderable)
            except Exception:
                pass

    def set_tab_closers(self, closers):

        self.tabclosers = closers

        for data in self.pages:
            page, label_tab, status, label_tab_menu = data
            label_tab.set_onclose(self.tabclosers)

    def show_images(self, show_image=True):

        self._show_image = show_image

        for data in self.pages:
            page, label_tab, status, label_tab_menu = data
            label_tab.show_image(self._show_image)

    def set_tab_angle(self, angle):

        if angle == self.angle:
            return

        self.angle = angle

        for data in self.pages:
            page, label_tab, status, label_tab_menu = data
            label_tab.set_angle(angle)

    def set_tab_pos(self, pos):
        self.Notebook.set_tab_pos(pos)

    def OnKeyPress(self, widget, event):

        if event.state & (Gdk.ModifierType.MOD1_MASK | Gdk.ModifierType.CONTROL_MASK) != Gdk.ModifierType.MOD1_MASK:
            return False

        if event.keyval in [Gdk.keyval_from_name("Up"), Gdk.keyval_from_name("Left")]:
            self.prev_page()
        elif event.keyval in [Gdk.keyval_from_name("Down"), Gdk.keyval_from_name("Right")]:
            self.next_page()
        else:
            return False

        widget.stop_emission_by_name("key_press_event")

        return True

    def append_page(self, page, label, onclose=None, angle=0, fulltext=None):

        self.set_tab_angle(angle)
        closebutton = self.tabclosers

        label_tab = ImageLabel(
            label, self.images["empty"], onclose, closebutton=closebutton,
            angle=angle, show_image=self._show_image, statusimage=None,
            show_status_image=self._show_status_image
        )

        if fulltext is None:
            fulltext = label

        label_tab.set_tooltip_text(fulltext)

        # menu for all tabs
        label_tab_menu = ImageLabel(label, self.images["empty"])

        self.pages.append([page, label_tab, 0, label_tab_menu])

        eventbox = gtk.EventBox()
        eventbox.set_visible_window(False)

        label_tab.show()

        eventbox.add(label_tab)
        eventbox.show()
        eventbox.set_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        eventbox.connect('button_press_event', self.on_tab_click, page)

        gtk.Notebook.append_page_menu(self.Notebook, page, eventbox, label_tab_menu)

        self.Notebook.set_tab_reorderable(page, self.reorderable)
        self.Notebook.set_show_tabs(True)

    def remove_page(self, page):

        for i in self.pages[:]:
            if i[0] == page:
                gtk.Notebook.remove_page(self.Notebook, self.page_num(page))
                i[1].destroy()
                i[3].destroy()
                self.pages.remove(i)

                break

        if self.Notebook.get_n_pages() == 0:
            self.Notebook.set_show_tabs(False)

    def OnFocused(self, item):
        self.frame.Notifications.ClearPage(self, item)

    def on_tab_click(self, widget, event, child):
        pass

    def set_status_image(self, page, status):

        image = self.images[("offline", "away", "online")[status]]

        for i in self.pages:
            if page == i[0]:
                i[1].set_status_image(image)
                i[3].set_status_image(image)
                return

    def set_image(self, page, status):

        image = self.images[("empty", "hilite3", "hilite")[status]]

        for i in self.pages:
            if page == i[0]:

                if status == 1 and i[2] == 2:
                    return

                if i[2] != status:
                    i[1].set_image(image)
                    i[3].set_image(image)
                    i[2] = status

                return

    def set_text(self, page, label):

        for i in self.pages:
            if i[0] == page:
                i[1].set_text(label)
                i[3].set_text(label)
                return

    def set_text_colors(self, color=None):

        for i in self.pages:
            i[1].set_text_color(color)

    def set_text_color(self, page, color=None):

        for i in self.pages:
            if i[0] == page:
                i[1].set_text_color(color)
                return

    def dismiss_icon(self, notebook, page, page_num):

        page = self.get_nth_page(page_num)
        self.set_image(page, 0)
        self.set_text_color(page, 0)

    def request_hilite(self, page):

        current = self.get_nth_page(self.get_current_page())
        if current == page:
            return

        self.set_image(page, 2)
        self.set_text_color(page, 2)

    def request_changed(self, page):

        current = self.get_nth_page(self.get_current_page())
        if current == page:
            return

        self.set_image(page, 1)
        self.set_text_color(page, 1)

    def get_current_page(self):
        return self.Notebook.get_current_page()

    def set_current_page(self, page_num):
        return self.Notebook.set_current_page(page_num)

    def get_nth_page(self, page_num):
        return self.Notebook.get_nth_page(page_num)

    def page_num(self, page):
        return self.Notebook.page_num(page)

    def popup_enable(self):
        self.Notebook.popup_enable()

    def popup_disable(self):
        self.Notebook.popup_disable()

    def show(self):
        self.Notebook.show()


class PopupMenu(gtk.Menu):

    def __init__(self, frame=None, shouldattach=True):

        gtk.Menu.__init__(self)

        self.frame = frame
        self.user = None
        self.useritem = None
        self.handlers = {}
        self.editing = False

        # If the menu is not a submenu, it needs to be attached
        # to the main window, otherwise it has no parent
        if shouldattach and hasattr(self.frame, 'MainWindow'):
            self.attach_to_widget(self.frame.MainWindow, None)

    def setup(self, *items):

        for item in items:

            if item[0] == "":
                menuitem = gtk.SeparatorMenuItem()

            elif item[0] == "USER":

                menuitem = gtk.MenuItem.new_with_label(item[1])
                self.useritem = menuitem

                if len(item) >= 3:
                    self.handlers[menuitem] = menuitem.connect("activate", item[2])
                else:
                    menuitem.set_sensitive(False)

            elif item[0] == 1:

                menuitem = gtk.MenuItem.new_with_label(item[1])
                menuitem.set_submenu(item[2])

                if len(item) == 5 and item[4] is not None and item[3] is not None:
                    self.handlers[menuitem] = menuitem.connect("activate", item[3], item[4])
                elif item[3] is not None:
                    self.handlers[menuitem] = menuitem.connect("activate", item[3])

            elif item[0] == "USERMENU":

                menuitem = gtk.MenuItem.new_with_label(item[1])
                menuitem.set_submenu(item[2])

                if item[3] is not None:
                    self.handlers[menuitem] = menuitem.connect("activate", item[3])

                self.useritem = menuitem

            else:

                if item[0][0] == "$":
                    menuitem = gtk.CheckMenuItem.new_with_label(item[0][1:])
                elif item[0][0] == "#":
                    menuitem = gtk.MenuItem.new_with_label(item[0][1:])
                else:
                    menuitem = gtk.MenuItem.new_with_label(item[0])

                if len(item) >= 3 and item[2] is not None and item[1] is not None:
                    self.handlers[menuitem] = menuitem.connect("activate", item[1], item[2])
                elif item[1] is not None:
                    self.handlers[menuitem] = menuitem.connect("activate", item[1])

            self.append(menuitem)

            if item[0] != "":
                menuitem.set_use_underline(True)

            menuitem.show()

        return self

    def clear(self):

        for (w, widget) in self.handlers.items():
            w.disconnect(widget)

        self.handlers.clear()

        for widget in self.get_children():
            self.remove(widget)
            widget.destroy()

        if self.useritem is not None:
            self.useritem.destroy()
            self.useritem = None

    def set_user(self, user):
        self.user = user
        if self.useritem:
            self.useritem.get_child().set_text(user)

    def get_user(self):
        return self.user

    def OnSearchUser(self, widget):
        self.frame.SearchMethod.set_active_iter(self.frame.searchmethods[_("User")])
        self.frame.UserSearchCombo.get_child().set_text(self.user)
        self.frame.ChangeMainPage(None, "search")

    def OnSendMessage(self, widget):
        self.frame.privatechats.SendMessage(self.user, None, 1)
        self.frame.ChangeMainPage(None, "private")

    def OnShowIPaddress(self, widget):

        if self.user not in self.frame.np.ip_requested:
            self.frame.np.ip_requested.append(self.user)

        self.frame.np.queue.put(slskmessages.GetPeerAddress(self.user))

    def OnGetUserInfo(self, widget):
        self.frame.LocalUserInfoRequest(self.user)

    def OnBrowseUser(self, widget):
        self.frame.BrowseUser(self.user)

    def OnPrivateRoomAddUser(self, widget, room):
        self.frame.np.queue.put(slskmessages.PrivateRoomAddUser(room, self.user))

    def OnPrivateRoomRemoveUser(self, widget, room):
        self.frame.np.queue.put(slskmessages.PrivateRoomRemoveUser(room, self.user))

    def OnPrivateRoomAddOperator(self, widget, room):
        self.frame.np.queue.put(slskmessages.PrivateRoomAddOperator(room, self.user))

    def OnPrivateRoomRemoveOperator(self, widget, room):
        self.frame.np.queue.put(slskmessages.PrivateRoomRemoveOperator(room, self.user))

    def OnAddToList(self, widget):

        if self.editing:
            return

        if widget.get_active():
            self.frame.userlist.AddToList(self.user)
        else:
            self.frame.userlist.RemoveFromList(self.user)

    def OnBanUser(self, widget):

        if self.editing:
            return

        if widget.get_active():
            self.frame.BanUser(self.user)
        else:
            self.frame.UnbanUser(self.user)

    def OnBlockUser(self, widget):

        if self.editing:
            return

        if widget.get_active():
            self.frame.OnBlockUser(self.user)
        else:
            self.frame.OnUnBlockUser(self.user)

    def OnIgnoreIP(self, widget):

        if self.editing:
            return

        if widget.get_active():
            self.frame.OnIgnoreIP(self.user)
        else:
            self.frame.OnUnIgnoreIP(self.user)

    def OnIgnoreUser(self, widget):

        if self.editing:
            return

        if widget.get_active():
            self.frame.IgnoreUser(self.user)
        else:
            self.frame.UnignoreUser(self.user)

    def OnVersion(self, widget):
        self.frame.privatechats.SendMessage(self.user, "\x01VERSION\x01", bytestring=True)

    def OnCopyUser(self, widget):
        self.frame.clip.set_text(self.user, -1)

    def OnGivePrivileges(self, widget):

        self.frame.np.queue.put(slskmessages.CheckPrivileges())

        if self.frame.np.privileges_left is None:
            days = _("Unknown")
        else:
            days = self.frame.np.privileges_left // 60 // 60 // 24

        text = EntryDialog(
            self.frame.MainWindow,
            _("Give privileges") + " " + _("to %(user)s") % {"user": self.user},
            _("Give how many days of global privileges to this user?") + " (" + _("%(days)s days left") % {'days': days} + ")"
        )

        if text:
            try:
                days = int(text)
                self.frame.np.queue.put(slskmessages.GivePrivileges(self.user, days))
            except Exception as e:
                print(e)

    def OnPrivateRooms(self, widget):

        if self.user is None or self.user == self.frame.np.config.sections["server"]["login"]:
            return False

        items = []
        popup = self.frame.userlist.Popup_Menu_PrivateRooms
        popup.clear()
        popup.set_user(self.user)

        for room in self.frame.chatrooms.roomsctrl.PrivateRooms:

            if not (self.frame.chatrooms.roomsctrl.IsPrivateRoomOwned(room) or self.frame.chatrooms.roomsctrl.IsPrivateRoomOperator(room)):
                continue

            if self.user in self.frame.chatrooms.roomsctrl.PrivateRooms[room]["users"]:
                items.append(("#" + _("Remove from private room %s") % room, popup.OnPrivateRoomRemoveUser, room))
            else:
                items.append(("#" + _("Add to private room %s") % room, popup.OnPrivateRoomAddUser, room))

            if self.frame.chatrooms.roomsctrl.IsPrivateRoomOwned(room):

                if self.user in self.frame.chatrooms.roomsctrl.PrivateRooms[room]["operators"]:
                    items.append(("#" + _("Remove as operator of %s") % room, popup.OnPrivateRoomRemoveOperator, room))
                else:
                    items.append(("#" + _("Add as operator of %s") % room, popup.OnPrivateRoomAddOperator, room))

        popup.setup(*items)

        return True


def WriteLog(logsdir, fn, msg):

    oldumask = os.umask(0o077)
    if not os.path.exists(logsdir):
        os.makedirs(logsdir)

    logfile = open(os.path.join(logsdir, CleanFile(fn.replace(os.sep, "-")) + ".log"), 'ab', 0)

    os.umask(oldumask)

    text = "%s %s\n" % (time.strftime(NICOTINE.np.config.sections["logging"]["log_timestamp"]), msg)

    logfile.write(text.encode('UTF-8', 'replace'))
    logfile.flush()
    logfile.close()


size_suffixes = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']


def HumanSize(filesize):
    try:
        step_unit = 1024.0

        for i in size_suffixes:
            if filesize < step_unit:
                return "%3.1f %s" % (filesize, i)

            filesize /= step_unit
    except TypeError:
        return filesize


speed_suffixes = ['B/s', 'KiB/s', 'MiB/s', 'GiB/s', 'TiB/s', 'PiB/s', 'EiB/s', 'ZiB/s', 'YiB/s']


def HumanSpeed(filesize):
    try:
        step_unit = 1000.0

        for i in speed_suffixes:
            if filesize < step_unit:
                return "%3.1f %s" % (filesize, i)

            filesize /= step_unit
    except TypeError:
        return filesize


def Humanize(number):
    fashion = DECIMALSEP
    if fashion == "" or fashion == "<None>":
        return str(number)
    elif fashion == "<space>":
        fashion = " "
    number = str(number)
    if number[0] == "-":
        neg = "-"
        number = number[1:]
    else:
        neg = ""
    ret = ""
    while number[-3:]:
        part, number = number[-3:], number[:-3]
        ret = "%s%s%s" % (part, fashion, ret)
    return neg + ret[:-1]


def is_alias(aliases, cmd):
    if not cmd:
        return False
    if cmd[0] != "/":
        return False
    cmd = cmd[1:].split(" ")
    if cmd[0] in aliases:
        return True
    return False


def expand_alias(aliases, cmd):
    output = _expand_alias(aliases, cmd)
    return output


def _expand_alias(aliases, cmd):
    def getpart(line):
        if line[0] != "(":
            return ""
        ix = 1
        ret = ""
        level = 0
        while ix < len(line):
            if line[ix] == "(":
                level = level + 1
            if line[ix] == ")":
                if level == 0:
                    return ret
                else:
                    level = level - 1
            ret = ret + line[ix]
            ix = ix + 1
        return ""

    if not is_alias(aliases, cmd):
        return None
    try:
        cmd = cmd[1:].split(" ")
        alias = aliases[cmd[0]]
        ret = ""
        i = 0
        while i < len(alias):
            if alias[i:i + 2] == "$(":
                arg = getpart(alias[i + 1:])
                if not arg:
                    ret = ret + "$"
                    i = i + 1
                    continue
                i = i + len(arg) + 3
                args = arg.split("=", 1)
                if len(args) > 1:
                    default = args[1]
                else:
                    default = ""
                args = args[0].split(":")
                if len(args) == 1:
                    first = last = int(args[0])
                else:
                    if args[0]:
                        first = int(args[0])
                    else:
                        first = 1
                    if args[1]:
                        last = int(args[1])
                    else:
                        last = len(cmd)
                v = " ".join(cmd[first:last + 1])
                if not v:
                    v = default
                ret = ret + v
            else:
                ret = ret + alias[i]
                i = i + 1
        return ret
    except Exception as error:
        print(error)
        pass
    return ""
