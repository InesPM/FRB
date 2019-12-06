"""
A module to automate CIGALE. Currently works for a single galaxy.
It generates a configuration file and runs the standard pcigale
script. Requires pcigale already installed on the system. 
"""

import numpy as np
import sys, os, glob, multiprocessing
from collections import OrderedDict

from astropy.table import Table

from pcigale.session.configuration import Configuration
from pcigale.analysis_modules import get_module
from pcigale.data import Database
from pcigale.utils import read_table
from pcigale_plots import sed

from frb.surveys.catalog_utils import _detect_mag_cols, convert_mags_to_flux


_DEFAULT_SED_MODULES = ["sfhdelayed", "bc03", "nebular", "dustatt_calzleit", "dale2014", "restframe_parameters", "redshifting"]

#TODO Create a function to check the input filters
#Or create a translation file like eazy's.
#def check_filters(data_file):

def _sed_default_params(module):
    """
    Returns:
        params (dict): the default dict of SED modules
        and their initial parameters.
    """
    params = {}
    if module is "sfhdelayed":
        params['tau_main'] = (10**np.linspace(1,3,10)).tolist() #e-folding time of main population (Myr)
        params['age_main'] = (10**np.linspace(3,4,10)).tolist() #age (Myr)
        params['tau_burst'] = 50.0 #burst e-folding time (Myr)
        params['age_burst'] = 20.0
        params['f_burst'] = 0.0 #burst fraction by mass
        params['sfr_A'] = 0.1 #SFR at t = 0 (Msun/yr)
        params['normalise'] = False # Normalise SFH to produce one solar mass
    elif module is "bc03":
        params['imf'] = 1 #0: Salpeter 1: Chabrier
        params['metallicity'] = [0.0001, 0.0004, 0.004, 0.008, 0.02, 0.05] 
        params['separation_age'] = 10 # Separation between yound and old stellar population (Myr)
    elif module is 'nebular':
        params['logU'] = -2.0 # Ionization parameter
        params['f_esc'] = 0.0 # Escape fraction of Ly continuum photons
        params['f_dust'] = 0.0 # Fraction of Ly continuum photons absorbed
        params['lines_width'] = 300.0
        params['emission'] = True
    elif module is 'dustatt_calzleit':
        params['E_BVs_young'] = [0.12, 0.25, 0.37, 0.5, 0.62, 0.74, 0.86] #Stellar color excess for young continuum
        params['E_BVs_old_factor'] = 1.0 # Reduction of E(B-V) for the old population w.r.t. young
        params['uv_bump_wavelength'] = 217.5 #central wavelength of UV bump (nm)
        params['uv_bump_width'] = 35.0 #UV bump FWHM (nm)
        params['uv_bump_amplitude'] = 0.0 # Amplitude of the UV bump. For the Milky Way: 3.
        params['powerlaw_slope'] = 0.0 # Slope delta of the power law modifying the attenuation curve.
        params['filters'] = 'B_B90 & V_B90 & FUV'
    elif module is 'dale2014':
        params['fracAGN'] = [0.0,0.05,0.1,0.2]
        params['alpha'] = 2.0
    elif module is 'restframe_parameters':
        params['beta_calz94'] = False
        params['D4000'] = False
        params['IRX'] = False
        params['EW_lines'] = '500.7/1.0 & 656.3/1.0'
        params['luminosity_filters'] = 'u_prime & r_prime'
        params['colours_filters'] = 'u_prime-r_prime'
    elif module is 'redshifting':
        params['redshift'] = '' #Use input redshifts
    return params

def gen_cigale_in(photometry_table,zcol,infile="cigale_in.fits",overwrite=True):
    """
    Generates the input catalog from
    a photometric catalog.
    Args:
        photometry_table (astropy Table):
            A table from some photometric
            catalog with magnitudes and
            error measurements. Currently supports
            DES, DECaLS, SDSS, Pan-STARRS and WISE
        zcol (str):
            Name of the column with redshift
            esimates.
        infile (str, optional):
            Path to the CIGALE input file to
            be written into.
        overwrite (bool, optional):
            If true, overwrites file if it already exists
    """
    #Table must have a column with redshift estimates
    assert type(zcol)==str, "zcol must be a column name. i.e. a string"
    assert zcol in photometry_table.colnames, "{} not found in the table. Please check".format(zcol)
    magcols, mag_errcols = _detect_mag_cols(photometry_table)
    cigtab = photometry_table.copy()
    cigtab.rename_column(zcol,"redshift")
    photom_cols = magcols+mag_errcols
    #First rename columns to something CIGALE understands
    for col in photom_cols:
        #Rename W to WISE
        if "W" in col and "WISE" not in col:
            cigtab.rename_column(col,col.replace("W","WISE"))

            #DECaLS table also have a DECaLS-WISE xmatch
            if "DECaL" in col:
                cigtab[col][cigtab[col].mask]= -99.0
                cigtab.rename_column(col,col.replace("DECaL_",""))
        #Rename DES_Y to DES_y
        if "DES_Y" in col:
            cigtab.rename_column(col,col.replace("DES_Y","DES_y"))

    #Rename any column with "ID" in it to "id"
    idcol = [col for col in cigtab.colnames if "ID" in col][0]
    cigtab.rename_column(idcol,"id")
    #Rename 
    cigtab = convert_mags_to_flux(cigtab)
    cigtab = cigtab[['id','redshift']+photom_cols]

    cigtab.write(infile,overwrite=overwrite)
    return

def _initialise(data_file,config_file = "pcigale.ini",cores=None,sed_modules=_DEFAULT_SED_MODULES,sed_modules_params=None):
    """
    Initialise a CIGALE configuration file.
    
    Args:
        data_file (str):
            Path to the input photometry data file.
        config_file (str, optional):
            Path to the file where CIGALE's configuration
            is stored.
        cores (int, optional):
            Number of CPU cores to be used. Defaults
            to all cores on the system.
        sed_modules (list of 'str', optional): 
            A list of SED modules to be used in the 
            PDF analysis. If this is being input, there
            should be a corresponding correct dict
            for sed_modules_params.
        sed_module_params (dict, optional):
            A dict containing parameter values for
            the input SED modules. Better not use this
            unless you know exactly what you're doing.
    Returns:
        cigconf (pcigale.session.configuration.Configuration):
                CIGALE Configuration object
    """
    if sed_modules !=_DEFAULT_SED_MODULES:
        assert sed_modules_params is not None,\
             "If you're not using the default modules, you'll have to input SED parameters"
    cigconf = Configuration(config_file) #a set of dicts, mostly
    cigconf.create_blank_conf() #Initialises a pcigale.ini file

    # fill in initial values
    cigconf.pcigaleini_exists = True
    cigconf.config['data_file'] = data_file
    cigconf.config['param_file'] = ""
    cigconf.config['sed_modules'] = sed_modules
    cigconf.config['analysis_method'] = 'pdf_analysis'
    if cores is None:
        cores = multiprocessing.cpu_count() #Use all cores
    cigconf.config['cores'] = cores
    cigconf.generate_conf() #Writes defaults to config_file
    cigconf.config['analysis_params']['variables'] = ""
    cigconf.config['analysis_params']['save_best_sed'] = True
    cigconf.config['analysis_params']['lim_flag'] = True
    #Change the default values to new defaults:
    if sed_modules_params is None:
        sed_modules_params = {}
        for module in sed_modules:
            sed_modules_params[module] = _sed_default_params(module)
    cigconf.config['sed_modules_params'] = sed_modules_params
    cigconf.config.write() #Overwrites the config file

def run(photometry_table,zcol, data_file="cigale_in.fits", config_file="pcigale.ini",wait_for_input=False,
        plot=True,outdir=None,compare_obs_model=False,**kwargs):
    """
    Input parameters and run CIGALE.
    Args:
        photometry_table (astropy Table):
            A table from some photometric
            catalog with magnitudes and
            error measurements. Currently supports
            DES, DECaLS, SDSS, Pan-STARRS and WISE
        zcol (str):
            Name of the column with redshift
            esimates.
        data_file (str):
            Path to the input photometry data file.
        config_file: str, optional
            Path to the file where CIGALE's configuration
            is stored.
        wait_for_input (bool, optional):
            If true, waits for the user to finish
            editing the auto-generated config file
            before running.
        plot (bool, optional):
            Plots the best fit SED if true
        cores (int, optional):
            Number of CPU cores to be used. Defaults
            to all cores on the system.
        sed_modules (list of 'str', optional):
            A list of SED modules to be used in the 
            PDF analysis. If this is being input, there
            should be a corresponding correct dict
            for sed_modules_params.
        sed_module_params (dict, optional):
            A dict containing parameter values for
            the input SED modules. Better not use this
            unless you know exactly what you're doing.

    """
    gen_cigale_in(photometry_table,zcol,infile=data_file,overwrite=True)
    _initialise(data_file,config_file=config_file,**kwargs)
    if wait_for_input:
        input("Edit the generated config file {:s} and press any key to run.".format(config_file))
    cigconf = Configuration(config_file)
    analysis_module = get_module(cigconf.configuration['analysis_method'])
    analysis_module.process(cigconf.configuration)
    if plot:
        sed(cigconf,"mJy",True)

    if outdir is not None:
        try:
            os.system("rm -rf {}".format(outdir))
            os.system("mv out {:s}".format(outdir))
        except:
            print("Invalid output directory path. Output stored in out/")
    if compare_obs_model:
        #Generate an observation/model flux comparison table.
        photo_obs_model = Table()
        with Database() as base:
            filters = OrderedDict([(name, base.get_filter(name))
                                for name in cigconf.configuration['bands']
                                if not (name.endswith('_err') or name.startswith('line')) ])
            filters_wl = np.array([filt.pivot_wavelength
                                    for filt in filters.values()])
            mod = Table.read(outdir+'/results.fits')
            obs = read_table(cigconf.configuration['data_file'])
            photo_obs_model['lambda_filter'] = [wl/1000 for wl in filters_wl]
            photo_obs_model['model_flux'] = np.array([mod["best."+filt][0] for filt in filters.keys()])
            photo_obs_model['observed_flux'] = np.array([obs[filt][0] for filt in filters.keys()])
            photo_obs_model['observed_flux_err'] = np.array([obs[filt+'_err'][0] for filt in filters.keys()])
            photo_obs_model.write(outdir+"/photo_observed_model.dat",format="ascii",overwrite=True)
    return
