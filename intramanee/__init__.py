from intramanee.common.codes.models import *
from intramanee.common.models import *
from intramanee.common.utils import LOG

# Register is to be called

LOG.info("Initialize randd module")
import randd
import randd.documents
LOG.info("Initialize stock module")
import stock.documents
LOG.info("Initialize sales module")
import sales.documents
LOG.info("Initialize production module")
import production.documents
LOG.info("Initialize purchasing module")
import purchasing.documents
LOG.info("Initialize bot module")
import bot.documents

from intramanee.common import permissions as perm
