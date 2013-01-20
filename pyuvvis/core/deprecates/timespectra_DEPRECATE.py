''' Provides core TimeSpectra monkey-patched pandas DadtaFrame  to represent a set of spectral data.  Dataframe with spectral data 
along the index and temporal data as columns (and this orientation is enforced).  The spectral index is controlled from the specindex
module, which has a psuedo-class called SpecIndex (really a monkey patched Index).  Temporal data is stored using a DatetimeIndex or
a modified interval reprentation.  The need to support two types of temporal index, one of which is Pandas builtin DatetimeIndex is what led me
to not create a special index object (like SpecIndex).  Other spectral axis types (like Temperature axis) should probably be built close to the manner of 
Spec index.  The TimeSpectra dataframe actually stores enough information to go back an forth between DatetimeIndex and
Interval representations.  It does this by generating one or the other on the fly, and never relies on the current label object to generate teh next object.'''

import pandas

### Local imports (REPLACE WITH PYUVVIS IMPORTS)
from specindex import SpecIndex, specunits
from spec_labeltools import datetime_convert
from spec_labeltools import from_T, to_T, Tdic
from restore_utils import as_dataframe as adf

### These are used to overwrite pandas string formatting 
from StringIO import StringIO #For overwritting dataframe output methods
from pandas.util import py3compat
import pandas.core.common as com

## testing (DELETE)
from numpy.random import randn
from testimport import dates as testdates


### EVERYTHING NEEDS DEFAULTED TO NONE!  OTHERWISE, ANY OBJECT IMPORTED OR PASSED IN SEEMS TO HAVE THIS VALUE ASSIGNED.  THUS
### VALUE ASSIGNMENT NEEDS TO OCCUR WITHIN CONSTRUCTING METHODS AND FUNCTIONS
pandas.DataFrame.name=None
pandas.DataFrame.baseline=None

### Time related attributes
pandas.DataFrame.start=None  #MUST BE DATETIME/TIMESTAMPS or w/e is valid in pandas
pandas.DataFrame.stop=None #just make these start and stop? And imply canonical axis
pandas.DataFrame.periods=None
pandas.DataFrame.freq=None 
pandas.DataFrame._interval=None
pandas.DataFrame.timeunit=None

### Intensity types (Absorbance, Trasmittance, None)
pandas.DataFrame._itype=None
pandas.DataFrame._ref=None #Used for tracking intensity representations of data

### Time axis special attributes stuff
pandas.Index.unit=None
pandas.Index._kind=None  #Used to identify SpecIndex by other PyUvVis methods (don't overwrite)


tunits={'ns':'nanoseconds', 'us':'microseconds', 'ms':'milliseconds', 's':'seconds', 
          'm':'minutes', 'h':'hours','d':'days', 'y':'years'}


##########
##Errors##
##########
def TimeError(value):
    ''' Custom Error for when user tries to pass a bad spectral unit'''
    return NameError('Invalid time unit, "%s".  See df.timetypes for available units'%value)

def ItypeError(value):
    ''' Custom Error for when user tries to pass a bad spectral intensity style (T, %T, A etc...)'''
    return NameError('Invalid intensity type "%s".  See df.list_iunits() for valid spectral intenisty styles'%value)


##############################
## Spectral quantity output###
##############################
def _list_out(outdic, delim='\t'):
    ''' Generic output method for shortname:longname iterables.  Prints out various
    dictionaries, and is independent of the various datastructures contained'''
    print '\nKey',delim,'Description'
    print '-------------------\n'

    for (k,v) in sorted(outdic.items()):
        print k,delim,v
    print '\n'
    
def list_tunits(self, delim='\t'):
    ''' Print out all available temporal units in a nice format'''
    _list_out(tunits, delim=delim)
    
def list_iunits(self, delim='\t'):
    _list_out(Tdic, delim=delim)
    
### Self necessary here or additional df stuff gets printed   
def list_sunits(self, delim='\t'):
    ''' Print out all available units in a nice format'''
    _list_out(specunits, delim=delim)     

###################################
##Timeindex conversions functions##
###################################
def _as_datetime(timespectra):
    ''' Return datetimeindex from either stop,start or start, periods.'''

    if timespectra.stop:
        return pandas.DatetimeIndex(start=timespectra.start, end=timespectra.stop, freq=timespectra.freq)
    else:
        return pandas.DatetimeIndex(start=timespectra.start, periods=timespectra.periods, freq=timespectra.freq)

def as_datetime(self):
    ''' Return columns as DatetimeIndex'''
    self.columns=_as_datetime(self)
    self.columns._kind='temporal'    
    self._interval=False   
    

def _as_interval(timespectra, unit):#, unit=None):
    ''' Return columns as intervals as computed by datetime_convert function.  Not an instance method
   for calls from objects other than self.'''
    ### If current columns is DatetimeIndex, convert
    if timespectra._interval==False:
        return pandas.Index(datetime_convert(timespectra.columns, return_as=unit, cumsum=True))#, unit=unit)              

    ### If currently already intervals, convert to datetime, then convert that to new units
    else:
        newcols=_as_datetime(timespectra)
        return pandas.Index(datetime_convert(newcols, return_as=unit, cumsum=True))#, unit=unit)              
      
    ### Self necessary here or additional df stuff gets printed   
def as_interval(self, unit='interval'):  
    ''' Return columns as intervals as computed by datetime_convert function'''
    self.columns=_as_interval(self, unit)
    self.columns._kind='temporal'
    self._interval=True
    

################################
###Main psuedo spectral class###
################################
def TimeSpectra(*dfargs, **dfkwargs):
    ''' Function that returns a customized dataframe with a SpecIndex axis and a TimeIndex column.  SpecIndex is its own
    modified pandas Index object.  TimeSpectra stores temporal data in terms of either a DatetimeIndex or intervals, and enought
    metadata to transform between the represnetations.
    
    TimeSpectra attempts to leave the DataFrame initialization intact.  For example and empty TimeSpectra can be returned.'''

    ### Pop default DataFrame keywords before initializing###
    name=dfkwargs.pop('name', 'TimeSpectra')
    baseline=dfkwargs.pop('baseline', None)    

    ###Spectral index-related keywords
    specunit=dfkwargs.pop('specunit', None)
    
    ###Intensity data-related stuff
    iunit=dfkwargs.pop('iunit', None)
    ref=dfkwargs.pop('ref',None)  #SHOULD DEFAULT TO NONE SO USER CAN PASS NORMALIZED DATA WITHOUT REF

    ###Time index-related keywords  (note, the are only used if a DatetimeIndex is not passed in)
    freq=dfkwargs.pop('freq', None)    
    start=dfkwargs.pop('start', None)
    stop= dfkwargs.pop('stop', None)    
    periods=dfkwargs.pop('periods',None)
    timeunit=dfkwargs.pop('timeunit',None) #Not the same as freq, but inferred from it

    
    if stop and periods:
        raise AttributeError('TimeSpectra cannot be initialized with both periods and stop; please choose one or the other.')
    
    df=pandas.DataFrame(*dfargs, **dfkwargs)
    df.name=name
    df.baseline=baseline

    ###Set Index as spectral variables
    set_specunit(df, specunit)  #This will automatically convert to a spectral index
    

    ### If user passes non datetime index to columns, make sure they didn't accidetnally pass SpecIndex by mistake.
    if not isinstance(df.columns, pandas.DatetimeIndex):
        try:
            if df.columns._kind == 'spectral':
                raise IOError("SpecIndex must be passed as index, not columns.")   ### Can't be an attribute error or next won't be raised             
        
        ### df.columns has no attribute _kind, meaning it is likely a normal pandas index        
        except AttributeError:
            df._interval=True
            df.start=start
            df.stop=stop
            df.freq=freq
            df.timeunit=timeunit
            
    ### Take Datetime info and use to recreate the array
    else:
        df._interval=False        
        df.start=df.columns[0]
        df.stop=df.columns[-1]
        df.freq=df.columns.freq
        ### ADD TRANSLATION FOR FREQ--> basetimeuint
#       df.timeunit=get_time_from_freq(df.columns.freq)
        
    ### Have to do it here instead of defaulting on instantiation.
    df.columns._kind='temporal'
    
    ### Assign spectral intensity related stuff but 
    ### DONT CALL _set_itype function
    iunit=_valid_iunit(iunit)
    df._itype=iunit
    df._ref=ref
    
    
    return df


def _valid_iunit(sout):
    '''When user is switching spectral intensity units, make sure they do it write.'''
    if sout==None:
        return sout
    sout=sout.lower()
    if sout in Tdic.keys():
        return sout
    else:
        raise ItypeError(sout)    
    
def _ref_valid(ref, df):
    ''' Helper method for _set_itype() to handles various scenarios of valid references.  Eg user wants to 
    convert the spectral representation, this evaluates manually passed ref vs. internally stored one (maunal
    will overwrite upon completion in _set_itype). 
    
    Tries to first get ref from dataframe column name, then dataframe column index, then finally returns
    the array itself.  Does not type check if it is valid array object, since errors will be thrown inevitable downstream.
    
    Returns ref array'''
    
    if ref != None:
        r_temp=ref
    elif df._ref != None:
        r_temp=df._ref
    else:
        raise AttributeError('Cannot downconvert iunit from %s to %s without a reference spectrum.'%(Tdic[sin],Tdic[sout]))
    
    ### First, try ref is itself a column name
    try:
        rout=df[r_temp]
    except KeyError:
        pass
    
    ### If rtemp is an integer, return that column value.  
    ### NOTE: IF COLUMN NAMES ARE ALSO INTEGERS, THIS CAN BE PROBLEMATIC.
    if isinstance(r_temp, int):
        rout=df[df.columns[r_temp]]        

    ### Finally if ref is itself an array, just use it
    else:
        rout=r_temp    

    return rout

def _set_itype(df, sout, ref=None):
    '''Function used to change spectral intensity representation in a convertible manner. Not called on
    initilization of TimeSpectra(); rather, only called by as_iunit() method.'''
    
    sout=_valid_iunit(sout)
    sin=df._itype
    
    ########################################################################
    ### Case 1: User converting from full data down to referenced data.#####
    ########################################################################
    if sin==None and sout != None:
        rout=_ref_valid(ref, df)
        
        ### Divide by ref and convert spectrum
        df=divby(df, divisor=rout)
        df=df.apply(from_T[sout])
        
    
    ################################################################   
    ### Case 2: Changing spectral representation of converted data.#
    ################################################################     
    elif sin !=None and sout != None:
        df=df.apply(to_T[sin])
        df=df.apply(from_T[sout])
        rout=df._ref #For sake of consistent transferring at end of this function
        

    #############################################################    
    ### Case 3: User converting referenced data up to full data.#
    #############################################################
    elif sin !=None and sout==None:
        rout=_ref_valid(ref, df)
        df=df.apply(to_T[sin])
        df=df.mul(rout, axis=0)  #Multiply up!

    df._ref=rout       
    df._itype=sout
    
    return df
        
    

def __newrepr__(self):
    """
    Just ads a bit of extra data to the dataframe on printout.  Literally just copied directly from dataframe.__repr__ and
    added print statements.  Dataframe also has a nice ___reprhtml___ method for html accessibility.
    """
    delim='\t'
    if self.specunit==None:
        specunitout='None'
    else:
        specunitout=self.full_specunit
        
    print '**',self.name,'**', delim, 'Spectral unit:', specunitout, delim, 'Time unit:', 'Not Implemented','\n'
    
    buf = StringIO()
    if self._need_info_repr_():
        self.info(buf=buf, verbose=self._verbose_info)
    else:
        self.to_string(buf=buf)
    value = buf.getvalue()

    if py3compat.PY3:
        return unicode(value)
    return com.console_encode(value)

### Using this method of property get and set makes it so that the user can access values via attribute style acces
### but not overwrite.  For example, if freq() is a funciton, dont' want user to do freq=4 and overwrite it.
### This is what would happen if didn't use property getter.  Setter is actually incompatible with DF so workaround it
### by using set_x methods.


### Spectral column attributes/properties
@property
def specunit(self):
    return self.index.unit    #Short name key

@property
def full_specunit(self):
    return specunits[self.index.unit]
    
def set_specunit(self, unit):
    self.index=self.index._convert_spectra(unit) 
        
@property
def spectypes(self):
    return specunits


### Temporal column attributes
@property
def timetypes(self):
    return tunits

### Intensity related data stuff
@property
def iunit(self):
    return self._itype

@property
def full_iunit(self):
    return Tdic[self._itype]

def as_iunit(self, unit, ref=None):
    ''' Changes the spectral intensity unit on the dataframe.  
    Cannot overwrite dataframe in place it seems (eg need to do return x instead of self=x.  Simply returns empty
    dataframe.  Therefore, instead of set_iunit, use as_iunit to imply the new object.'''
    if isinstance(unit, basestring):
        if unit.lower() in ['none', 'full']:
            unit=None

    dfout=_set_itype(self, unit, ref)
    ### Since _set_itype returned a new object, need to transfer some attributes
    ### _ref, _itype and stuff were already transferred by _set_itype


@property
def itypes(self):
    return Tdic




### Doesn't work
#def to_dataframe(self):
    #return adf(self)

### Set properties as instance methods ###
pandas.DataFrame.list_sunits=list_sunits
pandas.DataFrame.list_tunits=list_tunits
pandas.DataFrame.list_iunits=list_iunits

pandas.DataFrame.spectypes=spectypes                
pandas.DataFrame.specunit=specunit
pandas.DataFrame.full_specunit=full_specunit
pandas.DataFrame.set_specunit=set_specunit

pandas.DataFrame.iunit=iunit
pandas.DataFrame.itypes=itypes
pandas.DataFrame.as_iunit=as_iunit
pandas.DataFrame.full_iunit=full_iunit


pandas.DataFrame.timetypes=timetypes

pandas.DataFrame.as_interval=as_interval
pandas.DataFrame.as_datetime=as_datetime
#pandas.DataFrame.as_dataframe=to_dataframe



###Overwrite output representation
#pandas.DataFrame.__repr__=__newrepr__

#############################################
##Add Pyuvvis instance methods    ###########
##All methods must take df as first argument#
#############################################
### MUST BE ABSOLUTE IMPORTS
from pyuvvis.pyplots.advanced_plots import spec_surface3d, plot2d, plot3d
from pyuvvis.pyplots.basic_plots import specplot, range_timeplot
from pyuvvis.core.baseline import dynamic_baseline
from pyuvvis.core.spec_utilities import boxcar, wavelength_slices, divby

### PyUvVis plotting
pandas.DataFrame.spec_surface3d=spec_surface3d
pandas.DataFrame.plot3d=plot3d
pandas.DataFrame.plot2d=plot2d
pandas.DataFrame.specplot=specplot
pandas.DataFrame.range_timeplot=range_timeplot ## Is this one a problem?

#### Spectral Utilities
pandas.DataFrame.boxcar=boxcar
pandas.DataFrame.wavelength_slices=wavelength_slices
pandas.DataFrame.divby=divby

#### Baseline
pandas.DataFrame.dynamic_baseline=dynamic_baseline

### Correlation Analysis
## Intentionally leaving these out because the point is to return Sync and Async objects
#pandas.DataFrame.make_ref=pyuvvis.make_ref
#pandas.DataFrame.ca2d=pyuvvis.ca2d


if __name__ == '__main__':
    
    ### Be careful when generating test data from Pandas Index/DataFrame objects, as this module has overwritten their defaul behavior
    ### best to generate them in other modules and import them to simulate realisitc usec ase
    
    spec=SpecIndex([400,500,600])
    df=TimeSpectra(randn(3,3), columns=testdates, index=spec, specunit='k', timeunit='s', iunit='t', baseline=[1,2,3])
    df2=df.as_iunit('full', ref=0)
    df2=TimeSpectra(randn(3,3), columns=testdates, index=spec, specunit='k', timeunit='s')

    dfout=df.as_iunit('a')  #no ref
    print df
    
    


    df.as_interval('nanoseconds')
    df.set_specunit(None)
    df.set_specunit('FELLLAAA')

    #df=pandas.DataFrame([200,300,400])
    #print df
    #df.index=x  
    #df.con('centimeters')
    #print df
    
    
