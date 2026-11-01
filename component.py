"""Python UNO component entry point."""

import os
import sys

root = os.path.dirname(os.path.abspath(__file__))
if root not in sys.path:
    sys.path.insert(0, root)

import unohelper

from libreharp.sidebar import FACTORY, SidebarFactory
from libreharp.uno_app import PROOFREADER, PROTOCOL, Proofreader, ProtocolHandler

g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(Proofreader, PROOFREADER, ("com.sun.star.linguistic2.Proofreader",))
g_ImplementationHelper.addImplementation(ProtocolHandler, PROTOCOL, ("com.sun.star.frame.ProtocolHandler",))
g_ImplementationHelper.addImplementation(SidebarFactory, FACTORY, ("com.sun.star.ui.UIElementFactory",))
