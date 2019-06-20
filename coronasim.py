# -*- coding: utf-8 -*-
"""
Created on Wed May 25 19:13:05 2016


@author: chgi7364
"""

# print('Loading Dependencies...')
import numpy as np
import os
import sys
# import copy
#
# import matplotlib as mpl
# mpl.use('qt4agg')
from matplotlib import pyplot as plt
# from mpl_toolkits.mplot3d import Axes3D
from itertools import cycle

# import chianti.core as ch
# from scipy import signal as scisignal
from scipy import io
from scipy import ndimage
from scipy import interpolate as interp
# from scipy.stats import norm
# import scipy.stats as stats
from scipy.optimize import curve_fit, approx_fprime, minimize_scalar, minimize
import copy

from scipy import integrate

# import warnings
# with warnings.catch_warnings():
#    warnings.simplefilter("ignore")
#    import astropy.convolution as con
# from numba import jit

from collections import defaultdict
from collections import OrderedDict
# import chianti.constants as const
# import chianti.util as cutil


import gridgen as grid
import progressBar as pb
import math
import time
import pickle
import glob
import warnings

warnings.simplefilter("ignore")

# from astropy import units as u
# import skimage as ski
# from skimage.feature import peak_local_max

# import multiprocessing as mp
# from multiprocessing import Pool
# from multiprocessing.dummy import Pool as ThreadPool
from functools import partial
# import platform
from mpi4py import MPI
import matplotlib as mpl

np.seterr(invalid='ignore')


def absPath(path):
    # Converts a relative path to an absolute path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, path)


####################################################################
##                          Environment                           ##
####################################################################

# Environment Class contains simulation parameters
# noinspection PyPep8Naming
class environment:
    # Environment Class contains simulation parameters

    # Locations of files to be used
    slash = os.path.sep
    datFolder = os.path.abspath("../dat/data/")

    def_Bfile = os.path.join(datFolder, 'mgram_iseed0033.sav')
    def_bkFile = os.path.join(datFolder, 'gilly_background_cvb07.dat')
    def_ioneq = os.path.join(datFolder, 'formattedIoneq.tsv')
    def_abund = os.path.join(datFolder, 'abundance.tsv')
    def_ionpath = os.path.abspath('../dat/chianti/chiantiData/')
    def_hahnFile = os.path.join(datFolder, 'hahnData.txt')
    def_2DLOSFile = os.path.join(datFolder, 'vxnew_2D_gilly40401.sav')
    def_ionFile = os.path.join(datFolder, 'useIons.csv')
    def_collisPath = os.path.join(datFolder, 'collisions.dat')
    def_solarSpecFileHigh = os.path.abspath(os.path.join(datFolder, 'solarSpectrum/xIsun_whole.dat'))
    def_solarSpecFileLow = os.path.abspath(os.path.join(datFolder, 'solarSpectrum/EVE_L3_merged_2017347_006.fit'))
    # def_solarSpecFileLong = os.path.abspath(os.path.join(datFolder, 'solarSpectrum/recent.txt'))

    def_magPath = os.path.abspath('../dat/magnetograms')
    def_rmsPath = os.path.join(datFolder, 'vrms_table_zephyr.dat')

    # For doing high level statistics
    fullMin = 0
    fullMax = 0
    fullMean = 0
    fullMedian = 0
    mapCount = 0

    zLabel = r"Height above Photosphere ($R_\odot$)"

    # For randomizing wave angles/init-times
    primeSeed = 27
    randOffset = 0

    timeRand = np.random.RandomState(primeSeed * 2)
    streamRand = np.random.RandomState()  # Gets seeded by streamindex
    primeRand = np.random.RandomState(primeSeed)

    # Constants
    c = 2.998e10  # cm/second (base velocity unit is cm/s)
    hev = 4.135667662e-15  # eV*s
    hergs = 6.626e-27  # ergs*sec
    hjs = 6.626e-34  # Joules*sec
    KB = 1.380e-16  # ergs/Kelvin
    K_ev = 8.6173303e-5  # ev/Kelvin
    r_Mm = 695.5  # Rsun in Mega meters
    r_Cm = r_Mm * 10 ** 8
    mH = 1.67372e-24  # grams per hydrogen
    mE = 9.10938e-28  # grams per electron
    mP = 1.6726218e-24  # grams per proton
    amu = 1.6605e-24  # Grams per amu
    rtPi = np.sqrt(np.pi)

    # Parameters
    rstar = 1
    B_thresh = 6.0
    fmax = 8.2
    theta0 = 28.5921
    S0 = 7.0e5

    maxEnvs = 100
    maxIons = 100
    weightPower = 2
    shrinkEnv = True

    # for plotting
    lastPos = 1e8
    plotMore = True

    psfSig = 0.047  # Angstroms

    def __init__(self, bkFile=None, name="Default"):
        # Initializes
        self.name = name
        self.reset_mpi()

        if self.root:
            print('Initializing {}:'.format(name))

            # Load in the plasma parameters
            self._plasmaLoad(bkFile)

            # Load in solar spectral data
            self.spectrumLoad()

            # Do all the ion calculations and I/O: 40 mb
            self.ionLoad()

            # Load in the F files and the Hahn observations
            self.fLoad()
            self.fLoad_lin()
            self._hahnLoad()

            # Load in the Alfven wave information: 40 mb with shrink (double without)
            self._LOS2DLoad()

            # Load in all the bmaps: 40mb
            # self.loadAllBfiles()

        self.simulate_densities()

        if self.root:
            print("Done with Environment Initialization!")
            print('')

    def reset_mpi(self):
        comm = MPI.COMM_WORLD
        self.rank = comm.Get_rank()
        self.root = self.rank == 0
        self.size = comm.Get_size()

    ## File IO ##########################################################################
    def loadAllBfiles(self):
        """Load each of the Bfiles"""
        print('Loading Bmaps...', end='')
        sys.stdout.flush()

        mag_files = glob.glob(os.path.abspath(self.def_magPath + '/*.sav'))

        self.BXs = []
        self.BYs = []
        self.BMAPs = []
        self.BLABELs = []
        self.nBmap = 0

        if True:
            for file in mag_files:
                xx, yy, Braw = self.loadOneBfile(file)
                BMap_final, label_im = self.processOneBMap(Braw)
                self.BXs.append(xx)
                self.BYs.append(yy)
                self.BMAPs.append(BMap_final)
                self.BLABELs.append(label_im)
                self.nBmap += 1

        # if analyze: self.analyze_BMap2()
        print('ingested {}'.format(self.nBmap))

    def loadOneBfile(self, path):
        """Load in a single Bmap"""
        Bobj = io.readsav(path)
        xx = Bobj.get('x_cap')
        yy = Bobj.get('y_cap')
        Braw = Bobj.get('data_cap')

        if False:
            plt.imshow((np.abs(Braw)))
            plt.colorbar()
            plt.show()

        return xx, yy, Braw

    def processOneBMap(self, BMap_raw, thresh=0.9, sigSmooth=4, plot=False, addThresh=False):

        # Gaussian smooth the image
        if sigSmooth == 0:
            BMap_smoothed = BMap_raw
        else:
            BMap_smoothed = ndimage.filters.gaussian_filter(BMap_raw, sigSmooth)

        # Find all above the threshold and label
        bdata = np.abs(BMap_smoothed)
        blist = bdata.flatten().tolist()
        bmean = np.mean([v for v in blist if v != 0])
        bmask = bdata > bmean * thresh
        label_im_1, nb_labels_1 = ndimage.label(bmask)

        # Create seeds for voronoi
        coord = ndimage.maximum_position(bdata, label_im_1, np.arange(1, nb_labels_1))

        # Get voronoi transform
        label_im, nb_labels, voroBMap = self.__voronoify_sklearn(label_im_1, coord, bdata)

        if addThresh:
            # Add in threshold regions
            highLabelIm = label_im_1 + nb_labels
            label_im *= np.logical_not(bmask)
            label_im += highLabelIm * bmask

        # Clean Edges
        validMask = BMap_raw != 0
        label_im *= validMask
        voroBMap *= validMask
        BMap_final = voroBMap

        rawTot = np.nansum(np.abs(BMap_raw))
        proTot = np.nansum(BMap_final)
        bdiff = np.abs(rawTot - proTot)
        # print("\nThe total raw field is {:0.4}, and the total processed field is {:.4}".format(rawTot, proTot))
        # print("The ratio of processed over raw is {:.4}".format(proTot/rawTot))

        # Everything below is plotting/analysis
        if False:
            hist, edges = np.histogram(self.Bmap_means, 25)
            numLess = len([x for x in np.abs(self.Bmap_means) if x < 2])
            edges = edges[0:-1]
            fig, ax = plt.subplots()
            ax.step(edges, hist)
            ax.set_xlabel("Gauss")
            ax.set_ylabel('Number of Cells')
            ax.set_title('With Abs, Sum = {}, lessThan = {}'.format(np.sum(hist), numLess))
            plt.show()

        # fig, ax2 = plt.subplots()
        # pCons = self.mask(ax2, self.bFluxCons)
        # i5 = ax2.imshow(pCons, cmap = "RdBu", aspect = 'auto')
        # plt.colorbar(i5, ax = [ax2], label = "Percentage")
        # plt.show()

        if False:  # Plot Slice of Map
            fig, ax0 = plt.subplots()
            f2, ax = plt.subplots()

            # Detect Color Range
            f = 5
            st1 = np.std(voroBMap.flatten())
            m1 = np.mean(voroBMap.flatten())
            vmin = 0  # m1 - f*st1
            vmax = m1 + f * st1

            # Plot Raw Field Map
            image = label_im + 37
            newBmap = self.mask(ax0, image)
            i0 = ax0.imshow(newBmap, cmap='prism', aspect='auto', vmin=0)  # , vmin = vmin, vmax = vmax)
            plt.colorbar(i0, ax=[ax0], label='Index')  # , extend = 'max')
            ax0.set_title('Raw Magnetic Field')

            self.plotEdges(ax0, label_im)

            # Plot the Voromap
            newVoroBMap = self.mask(ax, voroBMap)
            i2 = ax.imshow((newVoroBMap), cmap='magma', interpolation='none',
                           aspect='equal')  # , vmin = vmin, vmax = vmax)
            ax.set_title('Final Field Map')

            self.plotEdges(ax, label_im)

            # Plot the maxima points
            coordinates = []
            for co in coord: coordinates.append(co[::-1])
            for co in coordinates:
                ax0.plot(*co, marker='o', markerfacecolor='r', markeredgecolor='k', markersize=6)
                ax.plot(*co, marker='o', markerfacecolor='w', markeredgecolor='k', markersize=6)

            plt.tight_layout()
            plt.colorbar(i2, ax=[ax], label='Gauss')  # , extend = 'max')
            plt.show()

        return BMap_final, label_im

    def _bfileLoad(self, Bfile, plot=False):
        """Depricated"""
        # Load Bmap
        if Bfile is None:
            self.Bfile = self.def_Bfile
        else:
            self.Bfile = self.__absPath(Bfile)
        self.thisLabel = self.Bfile.rsplit(os.path.sep, 1)[-1]

        print('Processing Environment: ' + str(self.thisLabel) + '...', end='', flush=True)
        print('')

        Bobj = io.readsav(self.Bfile)
        self.BMap_x = Bobj.get('x_cap')
        self.BMap_y = Bobj.get('y_cap')
        self.BMap_raw = Bobj.get('data_cap')

        if plot:
            plt.imshow((np.abs(self.BMap_raw)))
            plt.colorbar()
            plt.show()

    def _plasmaLoad(self, bkFile=None):
        print('Loading Plasma Stuff...', end='');
        sys.stdout.flush()
        # Load Plasma Background
        if bkFile is None:
            self.bkFile = self.def_bkFile
        else:
            self.bkFile = self.__absPath(bkFile)
        x = np.loadtxt(self.bkFile, skiprows=10)
        self.bk_dat = x
        self.rx_raw = x[:, 0]  # Solar Radii
        self.rho_raw = x[:, 1]  # g/cm^3
        self.ur_raw = x[:, 2]  # cm/s
        self.vAlf_raw = x[:, 3]  # cm/s
        self.T_raw = x[:, 4]  # K

        if False: self.zephyrPlot()


        # Calculate superradial expansion from zephyr
        self.expansionCalc()
        print("done")

    def zephyrPlot(self):
        fig, (ax1) = plt.subplots(1, 1, True)
        fig.set_size_inches(6,5)

        ax2 = ax1.twinx()
        # ax2.set_ylabel('Density', color='r')
        ax2.tick_params('y', colors='r')

        lns1 = ax1.plot(self.rx_raw - 1, np.log10(self.cm2km(self.ur_raw)),ls='solid', label='$\log_{10}$(Wind Speed [km/s])')
        lns2 = ax2.plot(self.rx_raw - 1, np.log10(self.rho_raw), 'r',ls='dotted', label='$\log_{10}$(Density [g/cm$^3$]) (Red Scale)')
        lns3 = ax1.plot(self.rx_raw - 1, np.log10(self.cm2km(self.vAlf_raw)),ls='dashed', label='$\log_{10}$(Alfvén Speed [km/s])')
        lns4 = ax1.plot(self.rx_raw - 1, np.log10(self.T_raw), ls='-.', label='$\log_{10}$(Temperature [K])')

        ax1.set_xscale('log')
        ax2.set_xscale('log')

        ax1.set_ylim((-2, 7))
        ax2.set_ylim((-23,-14))
        # ax1.set_yscale('log')
        # ax2.set_yscale('log')

        ax1.set_title('ZEPHYR Model Outputs')


        lns = lns1 + lns2 + lns3 + lns4
        labs = [l.get_label() for l in lns]
        ax1.legend(lns, labs, loc='lower center', frameon=False, bbox_to_anchor=(0.4,0))

        # ax1.legend()
        # ax2.legend()
        ax1.set_xlim([10 ** -2.5, 10 ** 2.5])
        self.solarAxis(ax1)

        # plt.title("Plasma Parameters from Zephyr")
        plt.tight_layout()
        plt.show()

    def solarAxis(self, ax, which=1):
        """Format the x axis to look nice"""
        ax.set_xscale('log')
        ax.xaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda x, pos: int(x) if x >= 1 else x))
        if which == 1:
            ax.set_xlabel(r"Height above Photosphere ($R_\odot$)")
        elif which == 2:
            ax.set_xlabel(r"Observation Height Above Photosphere ($R_\odot$)")

    def spectrumLoad(self):
        """Load the spectral data for the resonant profiles"""
        print('Loading Spectra...', end='');
        sys.stdout.flush()
        ##TODO find the correct absolute scaling for these measurements

        ###Load in the EVE data
        # from astropy.io import fits
        # hdulist = fits.open(self.def_solarSpecFileLow)
        # lamAx = hdulist[4].data['WAVELENGTH'].T.squeeze() #nm
        # units = hdulist[4].data['IRRADIANCE_UNITS'] #Watts/m^2/nm

        ##Average many of the EVE Spectra
        # intensity = np.zeros_like(hdulist[5].data[0]['SP_IRRADIANCE'])
        # averageDays = 365*2
        # succeed = 0
        # fail = 0
        # for ii in np.arange(averageDays):
        #    ints = hdulist[5].data[ii]['SP_IRRADIANCE']
        #    if -1 in ints: fail += 1; continue
        #    succeed += 1
        #    intensity += ints
        #    #if np.mod(succeed, 10) == 0: plt.plot(lamAx, ints, label = ii)
        # intensity /= succeed #Watts/m^2/nm

        # if False:
        #    plt.plot(lamAx, intensity,'k', label = 'Sum')
        #    plt.title("Tried: {}, Succeeded: {}, Failed: {}".format(averageDays, succeed, fail))
        #    plt.yscale('log')
        #    plt.show()
        #    #import pdb; pdb.set_trace()

        ##Attempt to put in correct units
        # lamAxLow = lamAx * 10 #angstrom
        # intensity #Watts/m^2/nm
        # solarSpecLow = intensity / 10 / 10000 /self.findSunSolidAngle(215)
        #                #W/cm^2/sr/Angstrom

        ##Load in the SUMER Spectral Atlas
        x = np.loadtxt(self.def_solarSpecFileHigh, skiprows=13)
        lamAxHigh = x[:, 0]  # Angstroms
        solarSpecHighRaw = x[:, 1]  # erg/s/cm2/sr/Angstrom
        solarSpecHigh = solarSpecHighRaw  # ergs/s/cm^2/sr/Angstrom

        ###Concatenate the two measurements
        ##Find the kink
        # lowMax = np.max(lamAxLow)
        # jj = 0
        # while lamAxHigh[jj] < lowMax:
        #    jj += 1
        # newLamAxHigh = lamAxHigh[jj:]
        # newSolarSpecHigh = solarSpecHigh[jj:]

        ##Make them match at the kink
        # last = solarSpecLow[-1]
        # first = solarSpecHigh[jj]
        # ratio = first/last
        # newsolarSpecLow = solarSpecLow * ratio

        # Concatenate
        # self.solarLamAx = np.concatenate((lamAxLow, newLamAxHigh))
        # self.solarSpec = np.concatenate((newsolarSpecLow, newSolarSpecHigh))

        if False:
            plt.plot(self.solarLamAx, self.solarSpec)
            plt.plot(lamAxHigh, solarSpecHigh)
            plt.axvline(lowMax, c='k')
            plt.yscale('log')
            plt.xscale('log')
            plt.show()

        # Create primary deliverable: Interpolation object
        self.solarLamAx = lamAxHigh  # Angstroms
        self.solarSpec = solarSpecHigh  # ergs/s/cm^2/sr/Angstrom
        # self.solarInterp = interp.interp1d(lamAxHigh, solarSpecHigh)#, kind='cubic') #ergs/s/cm^2/sr/Angstrom
        print('done')
        pass

    def returnSolarSpecLam(self, lowLam, highLam):
        try:
            ll = 0
            while self.solarLamAx[ll] < lowLam:
                ll += 1
            lowInd = ll
            while self.solarLamAx[ll] < highLam:
                ll += 1
            highInd = ll
            return self.solarLamAx[lowInd:highInd], self.solarSpec[lowInd:highInd]
        except:
            raise IndexError

    def returnSolarSpecLamFast(self, lowLam, highLam, lamAx, I0array):
        try:
            ll = 0
            while lamAx[ll] < lowLam:
                ll += 1
            lowInd = ll
            while lamAx[ll] < highLam:
                ll += 1
            highInd = ll
            return lamAx[lowInd:highInd], I0array[lowInd:highInd]
        except:
            raise IndexError

    def fLoad(self, fFile=None):
        if fFile is None: fFile = self.fFile
        f1File = os.path.join(self.datFolder, 'f_{}.txt'.format(fFile))
        x = np.loadtxt(f1File)

        self.fr = x[:, 0]
        self.f1_raw = x[:, 1]
        self.f2_raw = x[:, 2]
        self.f3_raw = x[:, 3]

    def fLoad_lin(self, fFile=None):
        if fFile is None: fFile = self.fFile_lin
        f1File = os.path.join(self.datFolder, 'f_{}.txt'.format(fFile))
        x = np.loadtxt(f1File)

        self.fr_lin = x[:, 0]
        self.f1_lin = x[:, 1]
        self.f2_lin = x[:, 2]
        self.f3_lin = x[:, 3]

    def fLoad_old(self, fFile):
        f1File = os.path.join(self.datFolder, 'f1_{}.txt'.format(fFile))
        f2File = os.path.join(self.datFolder, 'f2_{}.txt'.format(fFile))
        f3File = os.path.join(self.datFolder, 'f3_{}.txt'.format(fFile))
        x = np.loadtxt(f1File)
        y = np.loadtxt(f2File)
        z = np.loadtxt(f3File)
        self.fr = x[:, 0]
        self.f1_raw = x[:, 1]
        self.f2_raw = y[:, 1]
        self.f3_raw = z[:, 1]

        # print(f1File)
        # plt.plot(self.fr, self.f1_raw, label = "f1")
        # plt.plot(self.fr, self.f2_raw, label = "f2")
        # plt.axhline(1, color = 'k')
        # plt.legend()
        # plt.show()
        pass

    def fPlot(self):
        fig, ax = plt.subplots()
        ax.axhline(1, color='k', lw=0.5)


        c1 = 'royalblue'  #Wind
        c2= 'orange'    #Waves
        c3= 'darkred' #Thermal

        ax.plot(self.fr-1, self.f1_raw, c=c1, label=r'$W_{SW}^{(2)}$')# - Wind ($\rho^2$)')
        ax.plot(self.fr_lin - 1, self.f1_lin, c=c1, ls='--', label=r'$W_{SW}^{(1)}$')# - Wind ($\rho$)')

        ax.plot(self.fr-1, self.f2_raw, c=c2, label=r'$W_{Alf}^{(2)}$')# - Waves ($\rho^2$)')
        ax.plot(self.fr_lin - 1, self.f2_lin, c=c2, ls='--', label=r'$W_{Alf}^{(1)}$')# - Waves ($\rho$)')

        ax.plot(self.fr-1, self.f3_raw, c=c3, label=r'$W_{Th}^{(2)}$')# - Thermal ($\rho^2$)')
        ax.plot(self.fr_lin-1, self.f3_lin, c=c3, ls='--', label=r'$W_{Th}^{(1)}$')# - Thermal ($\rho$)')

        ax.set_xscale('log')
        ax.set_yscale('log')
        ax.set_xlim([0.01, 10])
        ax.set_ylim([0.5, 10])
        ax.legend(frameon=False)
        fig.set_size_inches(5, 4.5)

        import matplotlib.ticker as tk

        ax.yaxis.set_major_formatter(tk.LogFormatter())
        # ax.get_yaxis().get_minor_formatter().set_scientific(False)
        # ax.yaxis.set_minor_formatter(tk.FuncFormatter(lambda x, pos: int(x) if x >= 1 else str(np.round(x,3))))
        ax.yaxis.set_minor_formatter(tk.NullFormatter())
        self.solarAxis(ax, 2)
        # ax.set_xlabel('Observation Height Above Photosphere')
        plt.tight_layout()
        plt.show()

    def _hahnLoad(self):
        x = np.loadtxt(self.def_hahnFile)
        self.hahnAbs = x[:, 0]
        line1 = x[:, 1]
        line2 = x[:, 2]

        self.hahnPoints = line1
        self.hahnError = line2 - line1

    ##### Wave Stuff

    def _LOS2DLoad(self):
        """Load the 2D wave information from file"""
        print('Loading Wave information...', end='', flush=True)

        # Read in and store data
        x = io.readsav(self.def_2DLOSFile)
        self.R_ntime = x.ntime
        self.R_nzx = x.nzx
        self.R_time = x.time
        self.R_zx = x.zx

        self.xi1_t = self.R_time
        self.tmax = self.xi1_t[-1]

        if self.shrinkEnv:
            self.R_vlos = np.float32(x.vxlos)
        else:
            self.R_vlos = x.vxlos  # km/s

        # Create a normalized wave for above the top
        xi = self.R_vlos[-1, :].flatten()
        xistd = np.std(xi)
        xinorm = xi / xistd
        self.xi1_raw = xinorm

        # Extract the Vrms from each height
        rms = np.std(self.R_vlos, axis=1)
        normedV2D = (self.R_vlos.T / rms).T

        self.raw_rms = self.km2cm(rms)  # cm/s
        self.normedV2D = normedV2D  # unitless

        ###Make an extended rms curve

        ##Find the top
        # topInd = np.argmax(rms)
        # topZ = self.R_zx[topInd]
        # topRms = rms[topInd]

        ##make a flat line over the top
        # highZ = np.linspace(topZ, 150, 50)
        # highRMS = np.ones_like(highZ)*topRms #cm/s

        ##pull in data below the top
        # lowZ = self.R_zx[0:topInd]
        # lowRMS = rms[0:topInd] #cm/s

        ##put them together
        # self.flat_rms = np.concatenate((lowRMS, highRMS)) #cm/s
        # self.R_zx_long = np.concatenate((lowZ, highZ)) # Z

        # Load in the vrms curve we would like to use.
        self._vrmsLoad()

        # Plot the rms as fn of z
        if False:
            plt.figure()
            plt.semilogx(self.R_zx, self.raw_rms, label="Braid")
            plt.semilogx(self.vrms_z, self.vrms_v, label='Zephyr')
            np.savetxt("braidCalc.txt", (self.R_zx, self.raw_rms))

            plt.title("Flattening the RMS")
            plt.legend()
            plt.xlim((10 ** -2, 10 ** 1))
            # plt.ylim((20,70))
            plt.ylabel('cm/s')
            plt.xlabel('Z')
            plt.show()

        # Plot each of the time points seperately in normed and not normed case
        if False:
            skip = 20
            plt.figure()
            plt.title('Raw')
            plt.semilogx(self.R_zx, self.R_vlos[:, ::skip])
            plt.semilogx(self.R_zx, rms, 'k')
            plt.xlim((10 ** -2, 2))
            plt.xlabel('Z')
            plt.ylabel('km/s')

            plt.figure()

            plt.title('Normed')
            plt.semilogx(self.R_zx, normedV2D[:, ::skip])
            plt.xlim((10 ** -2, 2))
            plt.xlabel('Z')
            plt.ylabel('unitless')
            plt.show()

            # plt.imshow(self.R_vlos, origin = 'bottom')
            # plt.show()
            # plt.plot(self.xi1_t, self.xi1_raw)
            # plt.show()

        print('done')

        # self.plot2DV()

        pass

    def _vrmsLoad(self, rmsPath=None):
        if rmsPath is None: rmsPath = self.def_rmsPath

        x = np.loadtxt(rmsPath, skiprows=3)
        self.vrms_z = x[:, 0]  # Solar Radii
        self.vrms_v = self.km2cm(x[:, 1])  # cm/s

    def plot2DV(self):
        fig, ax = plt.subplots()
        mean = np.mean(self.R_vlos.flatten())
        std = np.std(self.R_vlos.flatten())
        sp = 4
        vmin = mean - sp * std
        vmax = mean + sp * std
        im = ax.pcolormesh(self.R_time, self.R_zx + 1, self.R_vlos, vmin=vmin, vmax=vmax, cmap='RdBu')
        cbar = fig.colorbar(im, ax=ax)
        cbar.set_label('km/s')
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('$R_{\odot}$')
        ax.set_title('Alfven Waves from Braid Code')
        plt.tight_layout()
        plt.show()

    # def findvRms(self, r):
    #    #RMS Velocity
    #    ind = np.searchsorted(self.vrms_z + 1, r) -1
    #    V = self.vrms_v[ind] #km/s
    #    return self.env.km2cm(V)

    def interp_vrms(self, r):
        """Return the rms wave amplitude at a given height in cm/s"""
        X = self.vrms_z + 1
        Y = self.vrms_v / np.sqrt(2) # cm/s #The sqrt gets rid of the 2d problem
        return self.interp(X, Y, r)

    ## Ion Stuff ##########################################################################

    def ionLoad(self):
        """Read the spreadsheet indicating the ions to be simulated"""
        print('Loading Ion information...', end='')
        sys.stdout.flush()
        self.ions = []

        import csv
        with open(self.def_ionFile) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if '#' in row['eString']:
                    continue
                for key in row.keys():
                    if not key.casefold() == 'estring':
                        if '.' in row[key]:
                            row[key] = float(row[key])
                        else:
                            row[key] = int(row[key])
                row['lamAx'] = self.makeLamAxis(row['ln'], row['lam0'], row['lamPm'])
                row['ionString'] = "{}_{}".format(row['eString'], row['ionNum'])
                row['fullString'] = "{}: {}".format(row['ionString'], row['lam0'])
                row['ionString+'] = r'${}^{{{}}}$'.format(row['eString'].title(), '+{}'.format(row['ionNum']-1))

                self.ions.append(row)

        self._chiantiLoad_all()
        self.assignColors()

    def assignColors(self, ions=None):
        """Give each ion a unique color"""
        # self.cList = ['r', 'darkorange', 'plum', 'g', 'b', 'darkviolet', 'magenta', 'firebrick', 'goldenrod', 'darkseagreen', 'slateblue', 'cornflowerblue', 'gold', 'cyan', 'c', 'm', 'lawngreen']

        self.cList = [(0,60,60), (150,0,90), (0,146,146), (200,0,0), (255,109,182), (0,109,219), (182,109,255), (120, 200,255), (190,255,255), (255,160,100), (230,230,80), (150,150,0), (36,255,36), (255,255,109)]

        modList = [np.divide(x, 255) for x in self.cList]
        nColors = len(self.cList)
        if ions is None:
            ions = self.ions
        for index, ion in enumerate(ions):
            ion['cNum'] = index
            ion['c'] = modList[index % nColors]
            ion['ls'] = '-'

        self.nIons = index

        if False:

            for index,color in enumerate(modList):
                plt.axhline(index, color=color)
            plt.show()

    def simulate_densities(self):
        """Calculate the densities in the solar atmosphere"""

        if self.root:
            # Restrict the number of ions to the few that are asked for
            self.ions = self.ions[:self.maxIons]

            # Create the list of unique elements to be simulated
            self.elements = dict()
            uniqueElementIons = []
            uniqueElementList = []
            for ion in self.ions:
                if not ion['eString'] in uniqueElementList:
                    uniqueElementList.append(ion['eString'])
                    uniqueElementIons.append(ion)

            workList = [(self, ion) for ion in uniqueElementIons]

            print("Simulating Elements: {}".format(uniqueElementList))
        else: workList = []

        # Simulate the elements in Parallel
        if self.size > 1:
            import masterslave as ms
            madeElements = ms.poolMPI(workList, element, True, True)
        else:
            madeElements = []
            for elem in workList:
                madeElements.append(element(elem))

        # Store the calculation
        if self.root:
            for elem in madeElements:
                self.elements[elem.name] = elem
            self.reset_mpi()

    def simulate_ionization(self, ion):
        #Depricated Serial Method
        # Load Recombination/Ionization Rates
        try:
            self.elements
        except:
            self.elements = dict()

        if not ion['eString'] in self.elements:
            self.elements[ion['eString']] = element(self, ion)
            return True
        else:
            print('Element Already Complete')
            return False
            # self.elements[ion['eString']].plotAll()

    def plot_ionization(self, ion=None):
        if ion is None:
            for ion in self.ions:
                self.plot_one_ionization(ion)
        else:
            self.plot_one_ionization(ion)

    def plot_one_ionization(self, ion):
        plt.figure()
        size = 1.8
        zAxis = np.logspace(-size, size, 300)
        dAxis = np.logspace(np.log10(3.3), np.log10(3.5), 50)
        print(self.elements[ion['eString']].densGrid)
        dAxis = np.insert(dAxis, 0, 1)
        dAxis.sort()

        dOne = self.elements[ion['eString']].getManyN(ion['ionNum'], 1, zAxis+1, eq=False)

        for dd in dAxis:
            if dd == 1: c = 'k'; lw = 3; zorder = 10
            else: c = None; lw = None; zorder = None
            Density = self.elements[ion['eString']].getManyN(ion['ionNum'], dd, zAxis+1, eq=False)
            modDensity = Density / dd
            normDensity = Density / dOne
            plt.loglog(zAxis, normDensity, c=c, lw=lw, zorder=zorder, label='{:0.4}'.format(np.round(dd, 2)))
        # plt.xlim((10**-2,10**2))
        # leg = plt.legend(loc='upper right')
        # leg.set_zorder(20)
        title = ion['ionString']
        plt.title(title)
        plt.xlabel("Z")
        plt.ylabel("Number Density")

        savePath = "../fig/2018/densfac"
        plt.savefig("{}/{}.png".format(savePath, title))
        plt.close()

    def getDensity(self, ion, densfac, rx, ionNum=None, **kwargs):
        if ionNum is None: ionNum = ion['ionNum']
        return self.elements[ion['eString']].getN(ionNum, densfac, rx, **kwargs)

    def getManyDensity(self, ion, densfac, rGrid, ionNum=None, **kwargs):
        if ionNum is None: ionNum = ion['ionNum']
        return self.elements[ion['eString']].getManyN(ionNum, densfac, rGrid, **kwargs)

    ##### Chianti Stuff
    def _chiantiLoad_all(self):
        """Load the chianti info for each of the desired ions"""

        for ion in self.ions:
            self.chiantiLoad(ion)

        print('done')

    def chiantiLoad(self, ion):
        """Load all of the data for a single ion"""

        ##Load things from files###############

        # Load the ionization fraction file
        self.cLoadIonFraction(ion)

        # Load in elemental abundance info
        self.cLoadAbund(ion)

        # Load in upsilon(T) info
        self.cLoadUpsilon(ion)

        # Load in statistical weights
        # self.cLoadStatWeight(ion) #Depricated

        # Load in Angular Momenta and Stat Weights
        self.cLoadAngularMomentum(ion)

        # Load the Einstein coefficients
        self.cLoadEinstein(ion)

        # Load the Ionization Potential
        self.cLoadIonization(ion)

        # Load the Recombination rate TO this ion
        self.cLoadRecombination(ion)

        # Load the collision rate
        self.cLoadCollision(ion)

        ##Do Calculations######################

        # Find the freezing density
        # self.findFreeze2(ion)   # Depricated?

        ##Make the Spectral Irradiance arrays
        self.makeIrradiance(ion)

        # Check if there are multiple lines here
        # self.checkOverlap(ion)
        return ion


        if False:  # Plot the info
            fig, ax1 = plt.subplots()
            # fig.subplots_adjust(right=0.8)
            ax2 = ax1.twinx()

            ax2.plot(ion['chTemps'], ion['chFracs'], 'bo-')
            ax2.set_xlabel('Temperature')
            ax2.set_ylabel('Fraction', color='b')
            ax2.tick_params('y', colors='b')

            ax1.plot(ion['splinedUpsX'], ion['splinedUps'], 'ro-')
            ax1.set_xlabel('Temperature')
            ax1.set_ylabel('Upsilon', color='r')
            ax1.tick_params('y', colors='r')

            plt.title("Data for {}_{}:{}->{} \n $\lambda$ = {}".format(ion['eString'], ion['ionNum'], ion['upper'],
                                                                       ion['lower'], ion['lam00']))

            height = 0.9
            left = 0.09
            plt.figtext(left, height + 0.06, "Abundance: {:0.4E}".format(ion['abundance']))
            plt.figtext(left, height + 0.03, "Weight: {}".format(ion['wi']))
            plt.show()

    def cLoadIonFraction(self, ion):
        """Load in the ionization fracion in equilibrium as per Chianti"""

        # Load in the ionization fraction info
        chi = np.loadtxt(self.def_ioneq)
        for idx in np.arange(len(chi[:, 0])):
            if chi[idx, 0] == ion['eNum'] and chi[idx, 1] == ion['ionNum']: break
        else:
            raise ValueError('{}_{} Not Found in fraction file'.format(ion['eString'], ion['ionNum']))

        ion['chTemps'] = chi[0, 2:]
        ion['chFracs'] = chi[idx, 2:] + 1e-100
        return ion['chTemps'], ion['chFracs']

    def cLoadAbund(self, ion):
        """Load the elemental abundance for this element"""
        abund = np.loadtxt(self.def_abund, usecols=[1])
        ion['abundance'] = 10 ** (abund[ion['eNum'] - 1] - abund[0])
        return ion['abundance']

    def cLoadUpsilon(self, ion):
        """Load in the upsilon(T) file"""
        fullstring = ion['eString'] + '_' + str(ion['ionNum'])
        ionpath = (self.def_ionpath + '/' + ion['eString'] + '/' + fullstring)
        fullpath = os.path.normpath(ionpath + '/' + fullstring + '.scups')

        getTemps = False
        getUps = False
        try:
            with open(fullpath) as f:
                for line in f:
                    data = line.split()
                    if getUps == True:
                        ion['ups'] = [float(x) for x in data]
                        break

                    if getTemps == True:
                        ion['upsTemps'] = [float(x) for x in data]
                        getUps = True
                        continue

                    if data[0] == str(ion['lower']) and data[1] == str(ion['upper']):
                        ion['upsInfo'] = [float(x) for x in data]
                        getTemps = True

            ion['splinedUpsX'] = np.linspace(0, 1, 200)

            ion['splinedUps'] = interp.spline(ion['upsTemps'], ion['ups'],
                                              ion['splinedUpsX'])

            # ion['gf'] = ion['upsInfo'][3]
        except:
            raise ValueError(
                'Transition {}_{}:{}->{} not found in scups file'.format(ion['eString'], ion['ionNum'], ion['upper'],
                                                                         ion['lower']))

        return ion['splinedUpsX'], ion['splinedUps']

    def cLoadAngularMomentum(self, ion):
        """Load in the angular momenta for the upper and lower levels"""
        fullstring = ion['eString'] + '_' + str(ion['ionNum'])
        ionpath = (self.def_ionpath + '/' + ion['eString'] + '/' + fullstring)
        fullpath2 = os.path.normpath(ionpath + '/' + fullstring + '.elvlc')
        found1 = False
        found2 = False
        with open(fullpath2) as f2:
            for line in f2:
                data = line.split()
                if data[0] == str(ion['lower']):
                    ion['JL'] = float(data[-3])
                    found1 = True
                if data[0] == str(ion['upper']):
                    ion['JU'] = float(data[-3])
                    found2 = True
                if found1 and found2: break
        if not found1: raise ValueError(
            'Angular Momemntum {}_{}:{} not found in elvlc file'.format(ion['eString'], ion['ionNum'], ion['lower']))
        if not found2: raise ValueError(
            'Angular Momemntum {}_{}:{} not found in elvlc file'.format(ion['eString'], ion['ionNum'], ion['upper']))

        ion['dj'] = ion['JU'] - ion['JL']
        j = ion['JL']

        if ion['dj'] == 1:
            ion['E1'] = ((2 * j + 5) * (j + 2)) / (10 * (j + 1) * (2 * j + 1))
            # ion['E1top'] = (2 * j + 5) * (j + 2)
            # ion['E1bottom'] = 10 * (j + 1) * (2 * j + 1)
        elif ion['dj'] == 0:
            ion['E1'] = ((2 * j - 1) * (2 * j + 3)) / (10 * j * (j + 1))
            # ion['E1top'] = (2 * j - 1) * (2 * j + 3)
            # ion['E1bottom'] = 10 * j * (j + 1)
        elif ion['dj'] == -1:
            ion['E1'] = ((2 * j - 3) * (j - 1)) / (10 * j * (2 * j + 1))
            # ion['E1top'] = (2 * j - 3) * (j - 1)
            # ion['E1bottom'] = 10 * j * (2 * j + 1)
        else:
            raise ValueError('Bad Change in Momentum')

        # Depricated, old style E
        ion['E'] = 1 - ion['E1'] / 4

        # Convert the momenta into statistical weights
        ion['wiU'] = 2 * ion['JU'] + 1
        ion['wi'] = 2 * ion['JL'] + 1

        # from fractions import Fraction
        # print('{}, {} E1 = {} = {}; E = {}'.format(fullstring, ion['lam00'], ion['E1'], str(Fraction(ion['E1']).limit_denominator()), str(Fraction(ion['E']).limit_denominator())))

        return ion['E1']

    def cLoadEinstein(self, ion):
        """Load in the Einstein Coefficients and the Chianti line wavelengths"""
        fullstring = ion['eString'] + '_' + str(ion['ionNum'])
        ionpath = (self.def_ionpath + '/' + ion['eString'] + '/' + fullstring)
        fullpath3 = os.path.normpath(ionpath + '/' + fullstring + '.wgfa')
        found = False
        with open(fullpath3) as f3:
            for line in f3:
                data = line.split()
                if data[0] == str(ion['lower']) and data[1] == str(ion['upper']):
                    ion['lam00'] = float(data[2])  # angstroms
                    ion['nu00'] = self.c / self.ang2cm(ion['lam00'])  # 1/s
                    ion['gf'] = float(data[3])  # dimensionless
                    ion['A21'] = float(data[4])  # inverse seconds
                    found = True
                    break
        if found == False: raise ValueError(
            'Einstein Coefficient for {}_{}:{} not found in wgfa file'.format(ion['eString'], ion['ionNum'],
                                                                              ion['lower']))

        ion['B21'] = ion['A21'] * self.c ** 2 / (
                2 * self.hergs * ion['nu00'] ** 3)  # 1/s * cm^2 / s^2 * 1/(ergs *s) * s^3 = cm^2 / (erg * s)
        ion['B12'] = ion['B21'] * ion['wiU'] / ion['wi']  # cm^2 / (erg*s)

        ion['fullString'] = "{}: {}".format(ion['ionString'], ion['lam00'])
        # print("A = {}, B21 = {}".format(ion['A21'], ion['B21']))
        # print('WiL: {}, WiU: {}'.format(ion['wi'], ion['wiU']))

    def checkOverlap(self, ion):
        '''See if there are any other lines of this ion nearby'''
        fullstring = ion['eString'] + '_' + str(ion['ionNum'])
        ionpath = (self.def_ionpath + '/' + ion['eString'] + '/' + fullstring)
        fullpath3 = os.path.normpath(ionpath + '/' + fullstring + '.wgfa')

        # Check for multiple overlapping lines
        dL = ion['lamPm']
        waveMin = ion['lam00'] - dL
        waveMax = ion['lam00'] + dL
        matchList = []
        with open(fullpath3) as f3:
            for line in f3:
                data = line.split()
                if len(data) < 2: break
                wavelength = float(data[2])
                if waveMin < wavelength < waveMax:
                    if int(data[0]) > 2: continue
                    delta = (float(data[2]) - ion['lam00']) / ion['I0Width']
                    matchList.append(
                        [int(data[0]), int(data[1]), float(data[2]), float('{:0.5}'.format(delta))])  # angstroms
        print('{}, num= {}\n {}'.format(fullstring, len(matchList), matchList))
        # print(ion['I0Width'])

    def cLoadIonization(self, ion):
        """Find the ionization potential for this ion"""  # TODO Check this is right
        ionizationPath = os.path.normpath('{}/ip/chianti.ip'.format(self.def_ionpath))

        with open(ionizationPath) as f:
            for line in f:
                data_raw = line.split()
                data = [float(x) if '.' in x else int(x) for x in data_raw]

                if data[0] == ion['eNum']:
                    if data[1] == ion['ionNum']:
                        thisE = data[2]  # cm^-1
                    if data[1] == ion['ionNum'] + 1:
                        nextE = data[2]  # cm^-1
                if data[0] > ion['eNum']:
                    break

        hc = 1.9864458e-16  # erg * cm
        ion['ionizationPotential'] = np.abs(thisE - nextE) * hc  # ergs

    def cLoadOneRecombRate(self, ionString, ionNum):
        '''Load in the recombination rate from ion ionNum, as a function of temperature'''
        higherString = "{}_{}".format(ionString, ionNum)
        ionpath = "{}/{}/{}/{}.rrparams".format(self.def_ionpath, ionString, higherString, higherString)
        fullpath = os.path.normpath(ionpath)
        # print('this is {} {}'.format(ionString,ionNum))
        try:
            with open(fullpath) as f:
                ii = 0
                lines = []
                for line in f:
                    if ii < 2: lines.append(line)
                    ii += 1
            type = int(lines[0].split()[0])
            params_raw = lines[1].split()[2:]
            params = [float(x) if '.' in x else int(x) for x in params_raw]

            if type == 1:
                params.pop(0)
                recomb_func = partial(self.recomb1, *params)
            elif type == 2:
                params.pop(0)
                recomb_func = partial(self.recomb2, *params)
            elif type == 3:
                recomb_func = partial(self.recomb3, *params)
            # else: notreal += 1

            recomb_T = np.logspace(3, 8, 100)  # Kelvin
            recomb = np.asarray([recomb_func(T) for T in recomb_T])  # cm^3/s

            # newx = np.logspace(3,8,500)
            # plt.plot(newx, [self.interp_recomb(ion, T) for T in newx])
            # plt.plot(ion['recomb_T'], ion['recomb'], 'ko')
            # plt.yscale('log')
            # plt.show()

        except:
            raise ValueError(
                'Recombination {}: {}->{} not found in rrparams file'.format(ionString, ionNum, ionNum - 1))
        return recomb_T, recomb

    def cLoadRecombination(self, ion):
        '''Load in the recombination rate to this ion'''
        ion['recomb_T'], ion['recomb'] = self.cLoadOneRecombRate(ion['eString'], ion['ionNum'] + 1)
        return ion['recomb_T'], ion['recomb']

    def cLoadOneCollisRate(self, thisElement, ionNum):
        """Load in the collisional ionization rate as F(T) out of ion ionNum"""
        path = self.def_collisPath
        with open(path) as f:
            for line in f:
                newLine = ''
                for letter in line:
                    if letter is 'D':
                        letter = 'E'
                    newLine = newLine + letter

                data = newLine.split('/')
                info = data[0].split(',')[1:3]
                info[1] = info[1][:-1]
                info = [int(x) for x in info]
                info[1] = info[0] - info[1] + 1

                element = info[0]
                ionum = info[1]
                values = [float(x) for x in data[1].split(',')]

                if element == thisElement and ionum == ionNum:
                    break

        # print('{}_{}: {}'.format(element, ionum, values))

        collis_T = np.logspace(3, 8, 100)  # Kelvin
        cFit = partial(self.collisFit, *values)
        collis = np.asarray([cFit(T) for T in collis_T])  # cm^3 /s
        return collis_T, collis

    def cLoadCollision(self, ion):
        """Load the collision rate as F(T)"""
        ion['collis_T'], ion['collis'] = self.cLoadOneCollisRate(ion['eNum'], ion['ionNum'])
        return ion['collis'], ion['collis_T']

    def makeIrradiance(self, ion):
        """Crop the appropriate section of the irradiance array"""
        rez = 1000  # int(2*ion['ln'])
        lam0 = ion['lam00']

        # First approximation, cut out the spectral line
        pm = 0.003 * lam0  # 2 * ion['lamPm']
        if lam0 < 700:
            pm *= 2
        if lam0 < 225:
            pm *= 2

        lamAxPrime, I0array = self.returnSolarSpecLam(lam0 - pm, lam0 + pm)  # ergs/s/cm^2/sr/Angstrom
        # lamAxPrime = np.linspace(lam0-pm, lam0+pm, rez)
        # I0array = self.solarInterp(lamAxPrime)

        # Fit a Gaussian to it
        fits, truncProfile = self.simpleGaussFit(I0array, lamAxPrime, lam0)

        # Find the wind limits
        vFast = self.interp_wind(40)

        lamPm = vFast / self.c * lam0
        lamHigh = lam0 + lamPm * 2
        lamLow = lam0 - lamPm * 2

        ion['I0Width'] = fits[2]

        spread = 8
        highLimit = lamHigh + spread * ion['I0Width']
        # highLimit = lam0 + spread*fits[2]
        # lowLimit = lam0 - spread*fits[2]
        lowLimit = lamLow - spread * ion['I0Width']

        # Store the Irradiance array
        # Watts/cm^2/sr/Angstrom

        ion['lamAxPrime'], ion['I0array'] = self.returnSolarSpecLam(lowLimit, highLimit)
        # ion['I0interp'] = interp.interp1d(ion['lamAxPrime'], ion['I0array'])#, kind='cubic') #ergs/s/cm^2/sr/Angstrom
        # ion['lamAxPrime'] = np.linspace(lowLimit, highLimit, rez)
        # ion['I0array'] = self.solarInterp(ion['lamAxPrime'])

        ion['nu0'] = self.c / self.ang2cm(lam0)
        ion['nuAx'] = self.lamAx2nuAx(ion['lamAx'])
        ion['nuAxPrime'] = self.lamAx2nuAx(ion['lamAxPrime'])
        ion['nuI0array'] = self.lam2nuI0(ion['I0array'], ion['lamAxPrime'])

        # plt.plot(ion['nuAxPrime'], ion['nuI0array'])
        # plt.title("{}_{}".format(ion['eString'], ion['ionNum']))
        # plt.show()
        if False:
            # Plot the irradiance array stuff
            plt.plot(lamAxPrime, I0array)
            plt.plot(lamAxPrime, self.gauss_function(lamAxPrime, *fits))
            # plt.plot(lamAxPrime, truncProfile)
            plt.axvline(lam0, c='grey')
            plt.axvline(lamHigh, c='grey', ls=':')

            plt.axvline(highLimit, c='k', ls='-')
            plt.axvline(lowLimit, c='k', ls='-')

            plt.plot(ion['lamAxPrime'], self.gauss_function(ion['lamAxPrime'], fits[0], lamHigh, fits[2], fits[3]))

            plt.axvline(lamLow, c='grey', ls=':')
            plt.axvline(lamLow - spread * fits[2], c='grey', ls='--')
            plt.plot(ion['lamAxPrime'], self.gauss_function(ion['lamAxPrime'], fits[0], lamLow, fits[2], fits[3]))

            plt.plot(ion['lamAxPrime'], ion['I0array'], "c.", lw=3)
            plt.title("{}_{}".format(ion['eString'], ion['ionNum']))
            plt.show()

    def lamAx2nuAx(self, lamAx):
        """Change a lamAx (ang) to a nuAx"""
        return self.c / self.ang2cm(lamAx)

    def nuAx2lamAx(self, nuAx):
        """Change a lamAx (ang) to a nuAx"""
        return self.c / nuAx * 10**8

    def lam2nuI0(self, I0, lamAx):
        """Change a ligt profile to frequency units"""
        nuAx = self.lamAx2nuAx(lamAx)
        return I0 * lamAx / nuAx

    def simpleGaussFit(self, profile, lamAx, lam0):
        sig0 = 0.2
        amp0 = np.max(profile) - np.min(profile)

        jj = 0
        while lamAx[jj] < lam0: jj += 1

        low = np.flipud(profile[:jj])
        high = profile[jj:]

        lowP = []
        last = low[0]
        for p in low:
            if p < last:
                lowP.append(p); last = p
            else:
                lowP.append(last)
        lowP = np.flipud(lowP)

        highP = []
        last = high[0]
        for p in high:
            if p < last:
                highP.append(p); last = p
            else:
                highP.append(last)

        truncProfile = np.concatenate((lowP, highP))

        popt, pcov = curve_fit(self.gauss_function, lamAx, truncProfile, p0=[amp0, lam0, sig0, 0])
        amp = popt[0]
        mu = popt[1]  # - lam0
        std = popt[2]
        b = popt[3]
        area = popt[0] * popt[2]
        return (amp, mu, std, b), truncProfile

    def gauss_function(self, x, a, x0, sigma, b):
        return a * np.exp(-(x - x0) ** 2 / (2 * sigma ** 2)) + b

    def collisFit(self, dE, P, A, X, K, T):
        U = dE / (self.K_ev * T)
        return A * (1 + P * np.sqrt(U)) / (X + U) * U ** K * np.exp(-U)  # cm^3/s

    def recomb1(self, A, B, T0, T1, T):
        TT0 = np.sqrt(T / T0)
        TT1 = np.sqrt(T / T1)
        return A / (TT0 * (1 + TT0) ** (1 - B) * (1 + TT1) ** (1 + B))

    def recomb2(self, A, B, T0, T1, C, T2, T):
        b = B + C * np.exp(-T2 / T)
        TT0 = np.sqrt(T / T0)
        TT1 = np.sqrt(T / T1)
        return A / (TT0 * (1 + TT0) ** (1 - b) * (1 + TT1) ** (1 + b))

    def recomb3(self, A, eta, T):
        return A * (T / 10000) ** (-eta)

    def findSunSolidAngle(self, rx):
        """Return the proportion of the sky covered by the sun"""
        return 0.5 * (1 - np.sqrt(1 - (1 / rx) ** 2))

    def particleTimes(self, ion, R):
        """Determine the Collision and the Expansion time at a Radius"""
        rs_cm = self.r_Mm * 10 ** 8

        rho = self.interp_rho(R)

        f = self.interp_rho
        e = 0.02
        drdrho = (f(R + e) - f(R)) / (e * rs_cm)
        T = self.interp_T(R)
        nE = rho / self.mP

        recomb = self.interp_recomb(ion, T)
        collis = self.interp_collis(ion, T)
        wind = self.interp_wind(R)
        t_C = 1 / (nE * (recomb + collis))  # Collisional Time
        t_E = np.abs(rho / (wind * drdrho))  # Expansion Time

        return t_C, t_E

    def particleTimeDiff(self, ion, R):
        """Determine the particle time difference"""
        t_C, t_E = self.particleTimes(ion, R)
        return np.abs(t_C - t_E)

    def printFreezeHeights(self):
        """Print all of the ions' freezing height"""
        print("Ion Freezing-in Radii:")
        for ion in self.ions:
            print("{}_{}: {:.4}".format(ion['eString'], ion['ionNum'], ion['r_freeze']))

    def findFreeze2(self, ion):
        """Determine the freezing radius and rho and T for an ion"""

        # Determine r_freeze
        func = partial(self.particleTimeDiff, ion)
        result = minimize_scalar(func, method='Bounded', bounds=[1.0002, 10])
        r_freeze = result.x

        ion['r_freeze'] = r_freeze
        ion['rhoCrit'] = self.interp_rho(r_freeze)
        ion['TCrit'] = self.interp_T(r_freeze)

        # Plot
        if False:
            print("{}_{}: {:.4}".format(ion['eString'], ion['ionNum'], ion['r_freeze']))

            fig, ax2 = plt.subplots()

            rr = np.linspace(1.05, 10, 1000)
            tt1 = []
            tt2 = []
            for r in rr:
                a, b = self.particleTimes(ion, r)
                tt1.append(a)
                tt2.append(b)

            ax2.axvline(r_freeze)
            ax2.plot(rr, tt1, label='Collision')
            ax2.plot(rr, tt2, label='Expansion')
            ax2.legend()
            ax2.set_title('Frozen in at R = {:.4}'.format(r_freeze))
            fig.suptitle('Finding the Freezing Height/Density for Ion: {}_{}'.format(ion['eString'], ion['ionNum']))
            ax2.set_yscale('log')
            ax2.set_xlabel('Impact Parameter')
            ax2.set_ylabel('Time')
            plt.show()

        pass

    def findFreezeAll(self, ions=None, densfac=1.0):
        """Find the places where the ions freeze-in"""
        doPlot = False
        # Set up evaluation Axis
        zaxis = np.logspace(-2, 1, 3000)
        raxis = zaxis + 1

        # Create the Figures
        if doPlot: fig1, (ax3, ax4) = plt.subplots(2,1, sharex=True)

        if ions is None:
            ions = self.ions
        for ion in ions:
            clr = ion['c']

            # Get the two density profiles
            nlte = self.getManyDensity(ion, densfac, raxis, eq=False, norm=True)
            absolute = self.getManyDensity(ion, densfac, raxis, eq=False, norm=False)

            ion['freezeHeightZ'], ion['freezeValue'] = self.findfreeze(zaxis, nlte)
            ion['floorHeightZ'], ion['floorValue'] = self.findFloor(zaxis, absolute)

            # Store values
            ion['freezeHeightR'] = ion['freezeHeightZ'] + 1
            ion['floorHeightR'] = ion['floorHeightZ'] + 1

            if doPlot:
                # Plot just the raw Densities
                ax3.loglog(zGrid, nlte, c=clr, label=ion['ionString'])
                # ax3.loglog(zGrid, equil, ls=':', c=clr)
                ax3.set_title("Raw Density Fraction")
                ax3.set_ylim([10 ** -7, 10 ** 0])

                # Plot Frozen
                ax4.semilogx(zGrid, nlte/nlte[-1], c=clr, label=ion['ionString'])
                ax4.set_title("Frozen Normalization")
                ax4.set_ylim([0.5, 1.5])

                #Plot freeze-in height
                ax3.scatter(xloc, value, marker='o', facecolors='none', edgecolors=clr)
                # ax4.scatter(xloc, tolerance, marker='o',facecolors='none', edgecolors=clr)

        if doPlot:
            # ax4.axhline(tolerance1, c='k', ls=':')
            # ax4.axhline(tolerance2, c='k', ls=':')
            ax3.legend(loc="upper left", bbox_to_anchor=(1, 1))
            self.solarAxis(ax4)
            ax4.set_xlim([10 ** -2, 10 ** 2])
            fig1.set_size_inches(8, 8)

            plt.tight_layout()
            plt.show()

            # # # Look at the ratio of the NEI to the Equilibrium
            # ratio = nlte / equil
            # ratio2 = equil / nlte
            # ax1.loglog(zGrid, ratio2, c=clr, label=ion['ionString'])
            # ax1.axhline(1, c='k', lw = 2)
            # ax1.set_title("Raw Ratio of equil/nlte")
            #
            # maxRats = [np.max((r1, r2))-1 for r1, r2 in zip(ratio, ratio2)]
            # ax2.loglog(zGrid, maxRats, c=clr, label=ion['ionString'])
            # # ax2.axhline(tol, c='k', ls=':', lw=2)
            # ax2.set_title("Only Positive Ratio")


            # # Plot a running Difference
            # difference = np.diff(nlte)
            # absoluteDifference = np.abs(difference)
            # absoluteDifference /= absoluteDifference[-1]
            # ax4.loglog(zGrid[:-1], absoluteDifference, c=clr, label=ion['ionString'])
            # ax4.set_title("Running Difference")
            # ax4.set_ylim([10 ** -3, 10 ** 7])


            # # Find the last inflection points
            # crossingInds = self.zcr(difference)  # Return indices of zero crossings
            # if False not in crossingInds:
            #     lastCrossInd = crossingInds[-1]  # Just keep the last crossing
            #
            #     lastCross = zGrid[lastCrossInd]  # Find z location of crossing and store
            #
            #
            #     # Plot
            #     lastValue = absoluteDifference[lastCrossInd]
            #     lastValue2 = nlte[lastCrossInd]
            #
            #     # print(ion['ionString'], ion['freezeHeight'])
            #     ax4.scatter(lastCross, lastValue, c=clr)
            #     ax3.scatter(lastCross, lastValue2, c=clr)


            #
            # # Find where the line is a certain percentage flat
            # tolerance = 100
            # inds = self.stepInd(absoluteDifference, tolerance)
            # if False not in inds:
            #     lastInd = inds[-1]
            #     xloc = zGrid[lastInd]
            #     value=nlte[lastInd]
            #     # print(xloc, value)
            #     ax3.scatter(xloc, value, marker='s',facecolors='none', edgecolors=clr)
            #     ax4.scatter(xloc, tolerance, marker='s',facecolors='none', edgecolors=clr)
            #
            #     ion['freezeHeight'] = xloc
            #     ion['freezeValue'] = value
            #
            # ax4.axhline(tolerance, c='k', ls='--')
        # self.save()
        pass

    def findfreeze(self, absiss, densArray, tol=0.1):
        '''Return the height and value of the ion freezing point'''

        # Normalize to Frozen
        frozenNorm = densArray / densArray[-1]

        # Find where the density is within TOL of frozen
        tolerance1 = 1 + tol
        tolerance2 = 1 - tol
        inds1 = self.stepInd(frozenNorm, tolerance1)
        inds2 = self.stepInd(frozenNorm, tolerance2)
        inds = []
        inds.extend(inds1)
        inds.extend(inds2)
        # inds = [*inds1, *inds2]
        inds.sort()

        # Find last crossing
        if len(inds) > 0:
            lastInd = inds[-1]

            # Get location and value at crossing
            xloc = absiss[lastInd]
            value = densArray[lastInd]

            return xloc, value
        else: return np.NaN, np.NaN

    def findFloor(self, zGrid, density):
        maxInd = np.argmax(density)
        floorHeight = zGrid[maxInd]
        floorVal = density[maxInd]
        return floorHeight, floorVal

    def stepInd(self, array, val):
        """Returns the index/indices where a threshold is crossed"""
        locs = array >= val
        if True in locs and False in locs:
            flips = np.nonzero(np.diff(locs))[0]
            return flips
        else: return []

    def zcr(self, y):
        """Returns the index/indices where zero is crossed"""
        locs = np.diff(np.sign(y)) != 0
        if True in locs:
            flips = np.nonzero(locs)[0]
            return flips
        else: return []

    ## Magnets ##########################################################################

    def __processBMap(self, BMap_raw, thresh=0.9, sigSmooth=4, plot=False, addThresh=False):
        # DEPRICATED
        # Gaussian smooth the image
        if sigSmooth == 0:
            self.BMap_smoothed = self.BMap_raw
        else:
            self.BMap_smoothed = ndimage.filters.gaussian_filter(self.BMap_raw, sigSmooth)

        # Find all above the threshold and label
        bdata = np.abs(self.BMap_smoothed)
        blist = bdata.flatten().tolist()
        bmean = np.mean([v for v in blist if v != 0])
        bmask = bdata > bmean * thresh
        label_im_1, nb_labels_1 = ndimage.label(bmask)

        # Create seeds for voronoi
        coord = ndimage.maximum_position(bdata, label_im_1, np.arange(1, nb_labels_1))

        # Get voronoi transform
        self.label_im, self.nb_labels, self.voroBMap = self.__voronoify_sklearn(label_im_1, coord, bdata)

        if addThresh:
            # Add in threshold regions
            highLabelIm = label_im_1 + self.nb_labels
            self.label_im *= np.logical_not(bmask)
            self.label_im += highLabelIm * bmask

        # Clean Edges
        self.validMask = self.BMap_raw != 0
        self.label_im *= self.validMask
        self.voroBMap *= self.validMask
        self.BMap = self.voroBMap

        rawTot = np.nansum(np.abs(self.BMap_raw))
        proTot = np.nansum(self.BMap)
        bdiff = np.abs(rawTot - proTot)
        # print("\nThe total raw field is {:0.4}, and the total processed field is {:.4}".format(rawTot, proTot))
        # print("The ratio of processed over raw is {:.4}".format(proTot/rawTot))

        if False:
            hist, edges = np.histogram(self.Bmap_means, 25)
            numLess = len([x for x in np.abs(self.Bmap_means) if x < 2])
            edges = edges[0:-1]
            fig, ax = plt.subplots()
            ax.step(edges, hist)
            ax.set_xlabel("Gauss")
            ax.set_ylabel('Number of Cells')
            ax.set_title('With Abs, Sum = {}, lessThan = {}'.format(np.sum(hist), numLess))
            plt.show()

        # fig, ax2 = plt.subplots()
        # pCons = self.mask(ax2, self.bFluxCons)
        # i5 = ax2.imshow(pCons, cmap = "RdBu", aspect = 'auto')
        # plt.colorbar(i5, ax = [ax2], label = "Percentage")
        # plt.show()

        if False:  # Plot Slice of Map
            fig, ax0 = plt.subplots()
            f2, ax = plt.subplots()

            # Detect Color Range
            f = 5
            st1 = np.std(self.voroBMap.flatten())
            m1 = np.mean(self.voroBMap.flatten())
            vmin = 0  # m1 - f*st1
            vmax = m1 + f * st1

            # Plot Raw Field Map
            image = label_im + 37
            newBmap = self.mask(ax0, image)
            i0 = ax0.imshow(newBmap, cmap='prism', aspect='auto', vmin=0)  # , vmin = vmin, vmax = vmax)
            plt.colorbar(i0, ax=[ax0], label='Index')  # , extend = 'max')
            ax0.set_title('Raw Magnetic Field')

            self.plotEdges(ax0, label_im)

            # Plot the Voromap
            newVoroBMap = self.mask(ax, self.voroBMap)
            i2 = ax.imshow((newVoroBMap), cmap='magma', interpolation='none',
                           aspect='equal')  # , vmin = vmin, vmax = vmax)
            ax.set_title('Final Field Map')

            self.plotEdges(ax, self.label_im)

            # Plot the maxima points
            coordinates = []
            for co in coord: coordinates.append(co[::-1])
            for co in coordinates:
                ax0.plot(*co, marker='o', markerfacecolor='r', markeredgecolor='k', markersize=6)
                ax.plot(*co, marker='o', markerfacecolor='w', markeredgecolor='k', markersize=6)

            plt.tight_layout()
            plt.colorbar(i2, ax=[ax], label='Gauss')  # , extend = 'max')
            plt.show()
            pass
        return

    def plotEdges(self, ax, map, domask=True):
        # Crude Edge Detection

        # map = self.label_im
        mask = np.zeros_like(map, dtype='float')
        width, height = mask.shape
        for y in np.arange(height):
            for x in np.arange(width):
                if x == 0 or x >= width - 1 or y == 0 or y >= height - 1:
                    mask[x, y] = np.nan
                else:
                    notedge = map[x, y] == map[x + 1, y]
                    if notedge: notedge = map[x, y] == map[x, y + 1]

                    if notedge:
                        mask[x, y] = np.nan
                    else:
                        mask[x, y] = 1

        # Plot the Edges
        my_cmap = copy.copy(plt.cm.get_cmap('gray'))  # get a copy of the gray color map
        my_cmap.set_bad(alpha=0)  # set how the colormap handles 'bad' values
        if domask:
            newMask = self.mask(ax, mask)
            ax.imshow(newMask, cmap=my_cmap, aspect='auto')
        else:
            ax.imshow(mask, cmap=my_cmap, aspect='auto')

    def mask(self, ax, array):
        almostmasked = np.asarray(array, 'float')
        almostmasked[~self.validMask] = np.nan
        masked = np.ma.masked_invalid(almostmasked)
        # ax.patch.set(hatch='x', edgecolor='black')
        return masked

    def __voronoify_sklearn(self, I, seeds, data):
        # label im, coords, bdata
        import sklearn.neighbors as nb
        # Uses the voronoi algorithm to assign stream labels
        tree_sklearn = nb.KDTree(seeds)
        pixels = ([(r, c) for r in range(I.shape[0]) for c in range(I.shape[1])])
        d, pos = tree_sklearn.query(pixels)
        cells = defaultdict(list)

        for i in range(len(pos)):
            cells[pos[i][0]].append(pixels[i])

        I2 = I.copy()  # Index number
        I3 = I.copy().astype('float32')  # Mean Flux
        I4 = I.copy().astype('float32')  # Flux Difference
        label = 0
        self.Bmap_means = []
        for idx in cells.values():
            idx = np.array(idx)
            label += 1

            mean_col = data[idx[:, 0], idx[:, 1]].mean()  # The mean value in the cell
            self.Bmap_means.append(mean_col)
            # npix = len(data[idx[:,0], idx[:,1]]) # num of pixels
            # sum_col = data[idx[:,0], idx[:,1]].sum() #The sum of the values in the cell
            # meanFlux = mean_col * npix
            # rawFlux = sum_col
            # bdiff = (meanFlux - rawFlux)/rawFlux #How much each cell is getting the flux wrong

            I2[idx[:, 0], idx[:, 1]] = label
            I3[idx[:, 0], idx[:, 1]] = mean_col
            # I4[idx[:,0], idx[:,1]] = bdiff

        return I2, label, I3  # , I4

    def analyze_BMap(self):
        # print('')
        # Find the number of pixels for each label
        labels = np.arange(0, self.nb_labels + 1) - 0.5
        hist, bin_edges = np.histogram(self.label_im, bins=labels)
        # Get rid of region zero
        hist = np.delete(hist, 0)
        labels = np.delete(labels, [0, self.nb_labels])

        ##Plot Hist
        # plt.bar(labels, hist)
        # plt.xlabel('Region Label')
        # plt.ylabel('Number of Pixels')
        # plt.show()

        # Find a histogram of the region areas in terms of pixel count
        bins2 = np.arange(0, np.max(hist))
        hist2, bin_edges2 = np.histogram(hist, bins=30)

        area_pixels = np.delete(bin_edges2, len(bin_edges2) - 1)

        ##Plot Hist
        # width = (area_pixels[1] - area_pixels[0])*0.8
        # plt.bar(area_pixels, hist2 , width = width)
        # plt.xlabel('Pixel Area')
        # plt.ylabel('Number of Regions')
        # plt.show()

        # Find the area of a pixel in Mm
        pixWidth_rx = np.abs(self.BMap_x[1] - self.BMap_x[0])
        pixWidth_Mm = self.r_Mm * pixWidth_rx
        pixArea_Mm = pixWidth_Mm ** 2

        # Convert the area in pixels to an equivalent radius in Mm
        area_Mm = area_pixels * pixArea_Mm
        radius_Mm = np.sqrt(area_Mm / np.pi)

        # Plot Hist

        plt.plot(radius_Mm, hist2, label=self.thisLabel)
        plt.title('Distribution of Region Sizes')
        plt.xlabel('Radius (Mm)')
        plt.ylabel('Number of Regions')
        plt.legend()
        # plt.show()

    def analyze_BMap2(self, NENV=6):
        fullMap = np.abs(self.BMap_smoothed.flatten())
        thisMap = [x for x in fullMap if not x == 0]

        min = np.min(thisMap)
        max = np.max(thisMap)
        mean = np.mean(thisMap)
        median = np.median(thisMap)

        bmin = 2
        bmax = 50

        inside = 100 * len([x for x in thisMap if bmin < x < bmax]) / len(thisMap)

        environment.fullMin += min
        environment.fullMax += max
        environment.fullMean += mean
        environment.fullMedian += median
        environment.mapCount += 1

        plt.hist(thisMap, histtype='step', bins=100, label="%s, %0.2f%%" % (self.thisLabel, inside))
        plt.show()
        if environment.mapCount == NENV:
            environment.fullMin /= NENV
            environment.fullMax /= NENV
            environment.fullMean /= NENV
            environment.fullMedian /= NENV

            plt.axvline(bmin)
            plt.axvline(bmax)
            plt.yscale('log')
            plt.xlabel('Field Strength (G)')
            plt.ylabel('Number of Pixels')
            plt.suptitle('Histograms of the Field Strengths')
            plt.title('Mean: ' + str(environment.fullMean) + ', Median: ' + str(environment.fullMedian) +
                      '\nMin: ' + str(environment.fullMin) + ', Max: ' + str(environment.fullMax))
            plt.legend()
            plt.show()

    def plotBmap(self):
        fig = plt.figure()

        map = copy.copy(self.BMap_raw)
        map[map == 0] = np.nan
        map = np.ma.masked_invalid(map)

        p0 = plt.pcolormesh(self.BMap_x, self.BMap_y, map, cmap='binary')
        ax = plt.gca()
        # ax.patch.set(hatch='x', edgecolor='black')
        ax.set_aspect('equal')
        plt.show()

    def plotXi(self):
        fig, (ax0, ax1) = plt.subplots(2, 1, True)

        ax0.plot(self.xi1_t, self.xi1_raw)
        ax1.plot(self.xi2_t, self.xi2_raw)
        ax1.set_xlabel('Time (s)')
        # ax0.set_ylabel()
        fig.text(0.04, 0.5, 'Wave Velocity (km/s)', va='center', rotation='vertical')

        plt.show()

    def expansionCalc(self):
        """Calculate the super-radial expansion from the Zephyr Inputs"""

        # self.B_calc = np.sqrt(4 * np.pi * self.rho_raw) * self.vAlf_raw  # Get B from Zephyr
        zx = np.asarray([rr - 1 for rr in self.rx_raw])
        B_analy = self.analyticB(zx) # Get B from analytic fit

        if False:
            fig, ax = plt.subplots()
            ax.loglog(zx, B_analy, label='Analytic')
            ax.loglog(zx, self.B_calc, label='Zephyr')
            plt.legend()
            self.solarAxis(ax)
            plt.show()

        self.B_calc = B_analy
        self.A_calc = 1 / self.B_calc  # Calculate flux tube area from that
        A0 = self.A_calc[0]
        F_raw = self.A_calc / (A0 * self.rx_raw ** 2)  # Compare flux tube area to radial expansion

        # Normalize the top
        F_norm = F_raw / F_raw[-1] * self.fmax

        # Truncate the bottom
        trunc = 0.855
        fcalc2 = copy.deepcopy(F_norm)
        fcalc2[fcalc2 < trunc] = trunc

        # Normalize the top and bottom
        scaleF = (fcalc2 - np.min(fcalc2)) / (np.max(fcalc2) - np.min(fcalc2))
        reScaleF = scaleF * (self.fmax - 1) + 1

        # Save variable
        self.F_raw = F_raw
        self.F_calc = reScaleF

        # Plotting
        if False:
            # plt.plot(self.rx_raw-1, F_norm, '--', label = "Calculated")
            # plt.plot(self.rx_raw-1, fcalc2,":", label = "Truncated")
            plt.plot(self.rx_raw - 1, reScaleF, label="Scaled")
            plt.plot(self.rx_raw - 1, F_raw, label="raw")
            plt.plot(self.rx_raw - 1, [self.getAreaF_analytic(b) for b in self.rx_raw], label="Old Fit Function")

            plt.legend()
            plt.xscale('log')
            # plt.xlim([0,50])
            plt.xlabel("$r/R_\odot$ - 1")
            plt.ylabel("Superadial expansion factor $f(r)$")
            plt.show()

    def analyticB(self, z):
        """Returns B in Gauss"""
        B = 3.578/(z + 1.)**3 + 7.9036/(z +1.)**5 + 1.1632/(z + 2.538)**2 + 1.1/np.exp(278.*(z - 0.0172))
        return B

    def getAreaF_analytic(self, r):
        Hfit = 2.2 * (self.fmax / 10.) ** 0.62
        return self.fmax + (1. - self.fmax) * np.exp(-((r - 1.) / Hfit) ** 1.1)

    def getAreaF(self, r):
        """Return the super-radial expansion F factor"""
        return self.interp_rx_dat(r, self.F_calc)

    def getAreaF_smooth(self, r):
        """Return the super-radial expansion F factor"""
        try: return self.fInterp(r)
        except: self.fInterp = interp.interp1d(self.rx_raw, self.F_calc, kind=5)
        return self.fInterp(r)

    def getAreaF_raw(self, r):
        """Return the super-radial expansion F factor"""
        return self.interp_rx_dat(r, self.F_raw)

    ## Light ############################################################################

    def makeLamAxis(self, Ln=100, lam0=200, lamPm=0.5):
        return np.linspace(lam0 - lamPm, lam0 + lamPm, Ln)

    def getIons(self, maxIons):
        if maxIons > len(self.ions):
            return self.ions
        return self.ions[0:maxIons]

    def findQt(self, ion, T):
        # Chianti Stuff
        Iinf = 2.18056334613e-11  # ergs, equal to 13.61eV
        kt = self.KB * T
        dE = self.ryd2erg(ion['upsInfo'][2])
        upsilon = self.findUpsilon(ion, T)
        return 2.172e-8 * np.sqrt(Iinf / kt) * np.exp(-dE / kt) * upsilon / ion['wi']

    def findQtIonization(self, ion, T):
        #
        # Chianti Stuff
        Iinf = 2.18056334613e-11  # ergs, equal to 13.61eV
        kt = self.KB * T
        dE = ion['ionizationPotential']
        upsilon = self.findUpsilon(ion, T)
        return 2.172e-8 * np.sqrt(Iinf / kt) * np.exp(-dE / kt) * upsilon / ion['wi']

    def findUpsilon(self, ion, T):
        Eij = ion['upsInfo'][2]  # Rydberg Transition energy
        K = ion['upsInfo'][6]  # Transition Type
        C = ion['upsInfo'][7]  # Scale Constant

        E = np.abs(T / (1.57888e5 * Eij))
        if K == 1 or K == 4: X = np.log10((E + C) / C) / np.log10(E + C)
        if K == 2 or K == 3: X = E / (E + C)

        Y = self.interp_upsilon(X, ion)
        if K == 1: Y = Y * np.log10(E + np.exp(1))
        if K == 3: Y = Y / (E + 1)
        if K == 4: Y = Y * np.log10(E + C)

        return Y

    ## Misc Methods #################################################################

    def smallify(self):
        self.label_im = []

    def save(self, name=None, fPath=None):
        if name is None: name = self.name
        print("Saving Environment: {}...".format(name), end='', flush=True)

        if fPath is None:
            # Check for directory
            savPath = os.path.abspath('../dat/envs/' + name)
            os.makedirs(savPath, exist_ok=True)
            fPath = os.path.join(savPath, name)

        # Save the environment itself
        envPath = fPath + '.env'
        if os.path.isfile(envPath):
            os.remove(envPath)
        with open(envPath, 'wb') as output:
            pickle.dump(self, output, pickle.HIGHEST_PROTOCOL)

        # Save contents of environment to text file
        infoEnv = self
        txtPath = fPath + '.txt'
        with open(txtPath, 'w') as output:
            output.write(time.asctime() + '\n\n')
            myVars = (infoEnv.__class__.__dict__, vars(infoEnv))
            for pile in myVars:
                for ii in sorted(pile.keys()):
                    if not callable(pile[ii]):
                        string = str(ii) + " : " + str(pile[ii]) + '\n'
                        output.write(string)
                output.write('\n\n')
        print('done', flush=True)

    def randomize(self):
        self.randOffset = int(self.primeRand.uniform(0, 10000))

    def setOffset(self, offset):
        self.randOffset = offset

    def __absPath(self, path):
        # Converts a relative path to an absolute path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        abs = os.path.join(script_dir, path)
        return abs

    def find_nearest(self, array, value):
        # Returns the index of the point most similar to a given value
        if not isinstance(array, np.ndarray):
            array = np.asarray(array)
        array = array - value
        np.abs(array, out=array)
        return array.argmin()

    def find_crossing(self, xx, A1, A2):
        A3 = np.abs(np.asarray(A1) - np.asarray(A2))
        return xx[A3.argmin()]

    # def find_nearest(self,array,value):
    #    idx = np.searchsorted(array, value, side="left")
    #    if idx > 0 and (idx == len(array) or math.fabs(value - array[idx-1]) < math.fabs(value - array[idx])):
    #        return idx-1
    #    else:
    #        return idx

    def interp_T(self, rx):
        return self.interp_rx_dat_log(rx, self.T_raw)  # K

    def interp_rho(self, rx):
        return self.interp_rx_dat_log(rx, self.rho_raw)  # g/cm^3

    def interp_wind(self, rx):
        return self.interp_rx_dat(rx, self.ur_raw)  # cm/s

    def interp_rx_dat_log(self, rx, array):
        return 10 ** (self.interp_rx_dat(rx, np.log10(array)))

    def interp_rx_dat(self, rx, array):
        # Interpolates an array(rx)
        if rx < 1.: return math.nan
        locs = self.rx_raw
        return self.interp(locs, array, rx)

    def interp_frac(self, T, ion):
        # Interpolate the ionization fraction as f(T)
        locs = ion['chTemps']
        func = np.log10(ion['chFracs'])
        temp = np.log10(T)

        # plt.plot(locs, func)
        # plt.xlabel('Temperature')
        # plt.ylabel('Fraction')
        # plt.show()
        return 10 ** self.interp(locs, func, temp)

    def interp_recomb(self, ion, T):
        # Interpolate the ionization fraction as f(T)
        locs = np.log10(ion['recomb_T'])
        func = np.log10(ion['recomb'])
        temp = np.log10(T)

        # plt.plot(locs, func)
        # plt.xlabel('Temperature')
        # plt.ylabel('Fraction')
        # plt.show()
        return 10 ** self.interp(locs, func, temp)

    def interp_collis(self, ion, T):
        # Interpolate the ionization fraction as f(T)
        locs = np.log10(ion['collis_T'])
        func = np.log10(ion['collis'])
        temp = np.log10(T)

        # plt.plot(locs, func)
        # plt.xlabel('Temperature')
        # plt.ylabel('Fraction')
        # plt.show()
        return 10 ** self.interp(locs, func, temp)

    def interp_w2_wind(self, b):
        # Figures out f1 as f(b)
        locs = self.fr
        func = self.f1_raw
        return self.interp(locs, func, b)

    def interp_w2_waves(self, b):
        # Figures out f1 as f(b)
        locs = self.fr
        func = self.f2_raw
        return self.interp(locs, func, b)

    def interp_w2_thermal(self, b):
        # Figures out f1 as f(b)
        locs = self.fr
        func = self.f3_raw
        return self.interp(locs, func, b)


    def interp_w1_wind(self, b):
        # Figures out f1 as f(b)
        locs = self.fr
        func = self.f1_lin
        return self.interp(locs, func, b)

    def interp_w1_waves(self, b):
        # Figures out f1 as f(b)
        locs = self.fr
        func = self.f2_lin
        return self.interp(locs, func, b)

    def interp_w1_thermal(self, b):
        # Figures out f1 as f(b)
        locs = self.fr
        func = self.f3_lin
        return self.interp(locs, func, b)

    def interp_ur(self, b):
        # Figures out ur as f(b)
        locs = self.rx_raw
        func = self.ur_raw
        return self.interp(locs, func, b) #cm/s

    def interp_upsilon(self, X, ion):
        # Figures out upsilon as f(X)
        locs = ion['splinedUpsX']
        func = ion['splinedUps']
        return self.interp(locs, func, X)

    def interp(self, X, Y, K):
        # Takes in X and Y and returns linearly interpolated Y at K
        if K >= X[-1] or K < X[0] or np.isnan(K): return np.nan
        TInd = int(np.searchsorted(X, K)) - 1
        if TInd + 1 >= len(Y): return np.nan
        val1 = Y[TInd]
        val2 = Y[TInd + 1]
        slope = val2 - val1
        step = X[TInd + 1] - X[TInd]
        discreteT = X[TInd]
        diff = K - discreteT
        diffstep = diff / step
        return val1 + diffstep * (slope)

    def interp_map(self, thisMap, envInd, x, y):
        xind = int(self.find_nearest(self.BXs[envInd], x))
        yind = int(self.find_nearest(self.BYs[envInd], y))
        return thisMap[envInd][xind][yind]

    # def interp_spectrum(self, lamAx):
    #    interp.interp1d()

    def cm2km(self, var):
        return var * 1e-5

    def km2cm(self, var):
        return var * 1e5

    def ang2cm(self, var):
        return var * 1e-8

    def cm2ang(self, var):
        return var * 1e8

    def ang2km(self, var):
        return var * 1e-13

    def km2ang(self, var):
        return var * 1e13

    def ryd2ev(self, var):
        return var * 13.605693

    def ryd2erg(self, var):
        return var * 2.1798723e-11

    def ryd2ang(self, var):
        return self.cm2ang(self.c * self.hev / self.ryd2ev(var))

    def get(self, myProperty, scaling='None', scale=10):
        prop = vars(self)[myProperty]
        if scaling.lower() == 'none':
            scaleProp = prop
        elif scaling.lower() == 'log':
            scaleProp = np.log10(prop) / np.log10(scale)
        elif scaling.lower() == 'root':
            scaleProp = prop ** (1 / scale)
        elif scaling.lower() == 'exp':
            scaleProp = prop ** scale
        else:
            print('Bad Scaling - None Used')
            scaleProp = prop
        return scaleProp

    def plot(self, property, abssisca=None, scaling='None', scale=10):
        scaleProp = self.get(property, scaling, scale)

        if abssisca is not None:
            abss = self.get(abssisca)
        else:
            abss = np.arange(len(scaleProp))

        plt.plot(abss, scaleProp)
        plt.title(property)
        grid.maximizePlot()
        plt.show()

    def plotElements(self, densfac=1.):

        for el in self.elements:
            if el in ['n']: continue
            self.elements[el].plotGrid(densfac)

    def plotTotals(self, doNorm=True):
        '''This just plots the total density for each of the ions'''
        densfac = 1
        zaxis = np.logspace(-1.9, 1)
        raxis = zaxis + 1

        fig,ax = plt.subplots(1,1)

        rho = np.asarray([self.interp_rho(rx)/self.mH for rx in raxis])
        nE = np.asarray([rh / self.mP for rh in rho])
        theNorm = nE[0] if doNorm else 1.
        ax.loglog(zaxis, nE/theNorm, c='k', label='nE')

        theNorm = rho[0] if doNorm else 1.
        ax.loglog(zaxis, rho/theNorm, 'c:', label='rho')


        for ion in self.ions:
            clr = ion['c']
            thisElement = self.elements[ion['eString']]
            n0 = thisElement.getManyN(0, densfac, raxis)
            theNorm = n0[0] if doNorm else 1.
            ax.loglog(zaxis, n0/theNorm, c=clr, label="{}_{}".format(ion['eString'], ion['ionNum']))

        ax.set_title("Ions")

        ax.legend(loc='lower left', ncol=2)

        self.solarAxis(ax)

        plt.tight_layout()
        plt.show()

    def plotChargeStates(self):
        """Plot the charge states for all the ions we are using as fn of height"""

        zaxis = np.logspace(-2, 1, 2500)
        raxis = zaxis + 1
        densfac = 1

        fig, (ax2, ax0, ax1) = plt.subplots(3,1, True, False)

        mpl.mathtext.SHRINK_FACTOR = 0.8
        mpl.rcParams['mathtext.default'] = 'regular'

        for index, ion in enumerate(self.ions):
            if index == 2: continue

            clr = ion['c']
            normalized = self.getManyDensity(ion, densfac, raxis, norm=True)
            absolute = self.getManyDensity(ion, densfac, raxis, norm=False)

            ax0.semilogx(zaxis, np.log10(normalized), ls=ion['ls'], c=clr, label=ion['ionString+'])
            ax1.semilogx(zaxis, np.log10(normalized/normalized[-1]), ls=ion['ls'], c=clr, label=ion['ionString+'])
            ax2.semilogx(zaxis, np.log10(absolute), ls=ion['ls'], c=clr, label=ion['ionString+'])

            ax0.plot(ion['freezeHeightZ'], np.log10(ion['freezeValue']), 'o', c=clr, markeredgecolor='k')
            ax2.plot(ion['floorHeightZ'], np.log10(ion['floorValue']), '^', c=clr, markeredgecolor='k')

        ax1.legend(loc='lower right', ncol=3, frameon=False)#, bbox_to_anchor=(0.7, 0.9))

        ax0.axhline(0, c='lightgray', ls='dashed')
        ax1.axhline(0, c='lightgray', ls='dashed', zorder=0)
        fig.set_size_inches(5.5,7.5)
        ax0.set_ylim((-6.5, 0.2))
        ax1.set_ylim((-9, 5))
        ax2.set_ylim((-4, 5))

        self.solarAxis(ax1)
        ax0.set_ylabel('$log_{{10}}(n_i\ /\ n_Z)$')
        ax1.set_ylabel('$log_{{10}}(n_i\ /\ n_Z\ /\ n_{fr})$')
        ax2.set_ylabel('$log_{{10}}(n_i)$')

        ax2.annotate('(a)', (0.9, 0.85), xycoords='axes fraction')
        ax0.annotate('(b)', (0.9, 0.15), xycoords='axes fraction')
        ax1.annotate('(c)', (0.9, 0.85), xycoords='axes fraction')

        ax0.set_xlim((0.007,10))
        ax2.set_title("NEI Ion Number Density")

        plt.tight_layout()
        plt.tight_layout()
        plt.show(True)
        mpl.mathtext.SHRINK_FACTOR = 0.7

    def plotSuperRadial(self):
        # self.expansionCalc()
        # Options
        cutHeight = 2
        width = 6

        # Create Figure
        fig, (ax0, ax1) = plt.subplots(2, 1, False, False)

        # Format Figure and Axis
        fig.set_size_inches(5.5, 6.1)
        ax0.set_ylim((0,width))
        ax0.set_xlim((-width,width))
        ax0.set_aspect('equal')

        ax0.annotate('(a)', (0.025, 0.9), xycoords='axes fraction')
        ax1.annotate('(b)', (0.025, 0.9), xycoords='axes fraction')

        # Draw the circle and cut line
        ax0.add_artist(plt.Circle((0,0),1, color = 'k', fill=False))
        ax0.axhline(cutHeight, color='k', ls='--')
        ax0.set_ylabel(r"$R_\odot$")
        # ax0.set_xlabel(r"Line of Sight ($R_\odot$)")

        # Plot delta along that cut
        rez = 500
        dist = 16
        position, target = [0, 0.001, cutHeight], [dist, 0.001, cutHeight]
        cutLine = grid.sightline(position, target, coords='cart')
        absiss = np.linspace(0, dist, rez)

        sRadColor = 'C4'
        radColor = 'C2'


        lineSim = simulate(cutLine, self, N=rez, findT=False, getProf=False, printOut=False)
        ax1.plot(absiss, np.rad2deg(lineSim.get('dangle')), '-', label='Super-Radial', c=sRadColor)
        ax1.plot(absiss, np.rad2deg(lineSim.get('pPos', 1)), ':', label='Radial', c=radColor)
        ax1.plot(absiss, np.rad2deg(lineSim.get('delta')), '--', label=r'Difference $\delta_{sup}$')
        ax1.axhline(0, c='k')


        ax1.legend(frameon=False)
        ax1.set_ylabel('Magnetic Projection (Degrees)')
        ax1.set_xlabel(r"Distance from Plane of Sky ($R_\odot$)")

        #Draw Field Lines
        holeBoundary = 28.6
        nLines = 13
        rootPoints = np.linspace(-holeBoundary, holeBoundary, nLines)
        rootPoints = [np.deg2rad(tt) for tt in rootPoints]
        rAx = np.linspace(1, 2 * width, 100)

        if True:  # Plot Radial Curves
            rPA = np.linspace(-2*holeBoundary, - holeBoundary, (nLines-1)/2)[:-1]
            rPB = np.linspace(holeBoundary, 2 *holeBoundary, (nLines-1)/2)[1:]
            roots = np.concatenate((rPA, rPB))
            rootPointsB = [np.deg2rad(tt) for tt in roots]

            for footTheta in rootPoints:
                    theta = np.ones_like(rAx) * footTheta
                    xx = [rr * np.sin(tt) for rr, tt in zip(rAx, theta)]
                    yy = [rr * np.cos(tt) for rr, tt in zip(rAx, theta)]
                    ax0.plot(xx, yy, c=radColor, ls=':', lw=0.9)

            # for footTheta in rootPointsB:
            #         theta = np.ones_like(rAx) * footTheta
            #         xx = [rr * np.sin(tt) for rr, tt in zip(rAx, theta)]
            #         yy = [rr * np.cos(tt) for rr, tt in zip(rAx, theta)]
            #         ax0.plot(xx, yy, c=radColor, ls = '-', lw=0.6)

        if True: # Plot the super-radial Curves
            fFunc = self.getAreaF_smooth(rAx)
            for footTheta in rootPoints:
                theta = np.arccos(1 - fFunc * (1 - np.cos(footTheta)))
                xx = [np.sign(footTheta) * rr * np.sin(tt) for rr, tt in zip(rAx, theta)]
                yy = [rr * np.cos(tt) for rr, tt in zip(rAx, theta)]
                ax0.plot(xx, yy, c=sRadColor, lw=0.9)


        if False:
            # Plot the noise evaluation
            fig, (ax2,ax3) = plt.subplots(2, sharex=True)
            rr = np.linspace(1,5,500)
            ff = [self.getAreaF(r) for r in rr]
            dif = np.diff(ff)
            ax2.plot(rr[:],ff,'o-', label = 'interpolated')
            ax2.plot(self.rx_raw[:-274], self.F_calc[:-274], 'o', label='True')
            plt.legend()

            ax3.plot(rr[:-1], dif)

        ax0.set_title("Superradial Magnetic Fields")
        plt.tight_layout()
        plt.show()

    def makeTable(self):
        """Figures out all of the data for the table we want to make"""
        import fractions
        for ion in self.ions:
            E1 = fractions.Fraction(ion['E1']).limit_denominator()
            ion['formTemp'] = self.elements[ion['eString']].findTForm(ion['ionNum'])
            foTemp = np.round(np.log10(ion['formTemp']),2)
            qt = np.round(np.log10(self.findQt(ion, ion['formTemp'])),2)

            R_fr = ion['freezeHeightR']


            print('{}\t &{}\t &{}\t &{:0.3}\t &{}\t &{:0.3}'.format(ion['ionString+'], ion['lam00'], foTemp, qt, E1, R_fr))

    def r2zAxis(self, rAxis):
        return [r - 1 for r in rAxis]

    def z2rAxis(self, zAxis):
        return [z + 1 for z in zAxis]




# envs Class handles creation, saving, and loading of environments
class envrs:

    # envs Class handles creation, saving, and loading of environments

    def __init__(self, name='Default'):
        self.name = name
        self.slash = os.path.sep
        self.savPath = os.path.abspath('../dat/envs/' + self.name)
        os.makedirs(self.savPath, exist_ok=True)
        self.filePath = os.path.abspath(self.savPath + self.slash + self.name)

        comm = MPI.COMM_WORLD
        self.rank = comm.Get_rank()
        self.root = self.rank == 0
        self.size = comm.Get_size()

        # self.envPath = os.path.normpath('../dat/magnetograms')

        return

    def __loadEnv(self, path):
        with open(path, 'rb') as input:
            return pickle.load(input)

    def __createEnvs(self, maxN=1e8):
        files = glob.glob(absPath(self.envPath + self.slash + '*.sav'))
        envs = []
        ind = 0
        for file in files:
            if ind < maxN: envs.append(environment(Bfile=file, name=self.name + '_' + str(ind)))
            ind += 1
        return envs

    def __saveEnvs(self, maxN=1e8):
        ind = 0
        os.makedirs(os.path.abspath(self.savPath), exist_ok=True)
        pathname = self.savPath + self.slash + self.name
        for env in self.envs:
            if ind < maxN: env.save(os.path.abspath(pathname + '_' + str(ind) + '.env'))
            ind += 1

        infoEnv = self.envs[0]
        with open(pathname + '.txt', 'w') as output:
            output.write(time.asctime() + '\n\n')
            myVars = (infoEnv.__class__.__dict__, vars(infoEnv))
            for pile in myVars:
                for ii in sorted(pile.keys()):
                    if not callable(pile[ii]):
                        string = str(ii) + " : " + str(pile[ii]) + '\n'
                        output.write(string)
                output.write('\n\n')

    def loadEnvs(self, maxN=1e8):
        files = glob.glob(absPath(self.savPath + os.path.normpath('/*.env')))
        self.envs = []
        ind = 0
        for file in files:
            if ind < maxN: self.envs.append(self.__loadEnv(file))
            ind += 1
        assert len(self.envs) > 0
        self.envs.mpi_reset()
        return self.envs

    def showEnvs(self, maxN=1e8):
        try:
            self.envs
        except:
            self.loadEnvs(maxN)
        # Print all properties and values
        ind = 0
        for env in self.envs:
            if ind < maxN:
                myVars = vars(env)
                print("\nEnv {} Properties".format(ind))
                for ii in sorted(myVars.keys()):
                    if isinstance(myVars[ii], str):
                        print(ii, " : ", myVars[ii].rsplit(os.path.sep, 1)[-1])
                for ii in sorted(myVars.keys()):
                    if not isinstance(myVars[ii], (str, np.ndarray)):
                        print(ii, " : ", myVars[ii])
                envVars = vars(environment)
                for ii in sorted(envVars.keys()):
                    if isinstance(envVars[ii], (int, float)):
                        print(ii, " : ", envVars[ii])
                ind += 1
                print("")
        return self.envs

    def Vars(self):
        return vars(self)

    def processEnvs(self, maxN=1e8, show=False):
        self.envs = self.__createEnvs(maxN)
        self.__saveEnvs(maxN)
        if show: plt.show(False)
        return self.envs

    ### Single Env Versions

    def processEnv(self, show=False):
        """Create a single environment"""
        self.env = environment(name=self.name, fFile=self.fFile)
        self.saveEnv()
        if show: plt.show(False)
        return self.env

    def saveEnv(self, filePath=None):
        """Save the Environment"""
        if filePath == None: filePath = self.filePath
        MPI.COMM_WORLD.barrier()
        if self.root:
            self.env.save(fPath=filePath)

    def loadEnv(self):
        """Load the Environment"""
        path = self.filePath + '.env'
        self.env = self.__loadEnv(path)
        self.env.reset_mpi()
        self.env.assignColors()
        return self.env


class element:
    minDens = 1e-100

    def __init__(self, work):
        env, ion = work

        self.env = env
        self.ion = ion

        # Get elemental data
        self.abundance = ion['abundance']
        self.mAtom = ion['mIon']
        self.nIons = ion['eNum'] + 1
        self.nLevels = self.nIons + 1
        self.name = ion['eString']

        self.loadRateLists()

        self.simulate_equilibrium()
        self.simulate_all_NLTE()

        # self.plotTimes()
        # self.plotAll()

    def simulate_equilibrium(self):
        """Find the equilibrium ionization balance for every temperature"""

        # Make a Height Axis
        self.nRGrid = 4000

        base = 10  #

        self.glob_zmin = 0.001
        self.glob_zmax = 100
        self.zGrid = np.logspace(np.log(self.glob_zmin) / np.log(base), np.log(self.glob_zmax) / np.log(base), self.nRGrid,
                                 base=base).tolist()
        self.rGrid = [z + 1 for z in self.zGrid]

        # Find the N_element as a function of height
        self.rhoGrid = [self.env.interp_rho(rx) for rx in self.rGrid]  # g/cm^3
        self.logRhoGrid = [np.log(r) for r in self.rhoGrid]

        nTotals = [self.abundance * rho / self.env.mP for rho in self.rhoGrid]  # 1/cm^3

        # Make a temperature axis as a function of height
        self.tGrid = [self.env.interp_T(rx) for rx in self.rGrid]

        ##Use this to see ionization vs temperature
        # self.tGrid = np.logspace(3,8,self.nRGrid)

        # Create an empty matrix
        nGrid = np.zeros((self.nLevels, self.nRGrid))
        normGrid = np.zeros_like(nGrid)

        print(nGrid.shape)

        for temp, nTot, jj in zip(self.tGrid, nTotals, np.arange(self.nRGrid)):
            # For every height point
            normSlice = self.chargeDistributionEq(temp)
            normGrid[:, jj] = normSlice
            nGrid[:, jj] = normSlice * nTot

        # Store Equilibrium Values
        self.nGrid = nGrid  # 1/cm^3, [ionNum, r]
        self.normGrid = normGrid

        if False:
            ## Did the equilibrium calculation total density match the zephyr inputs?
            plt.figure()
            absiss = self.zGrid # Plot against what axis

            # Plot just the raw zephyr density
            plt.plot(absiss, nTotals, label='rho*abund/mAtom')

            # Sum the calculated equilibrium densities
            justStates = copy.copy(nGrid)
            justStates[0, :] = 0
            summedEquil = np.sum(justStates, axis=0)

            plt.plot(absiss, summedEquil, '--', label='sum(n_i)')
            plt.yscale('log')
            plt.xscale('log')
            plt.legend()
            plt.title('Did the equilibrium calculation match the zephyr inputs?')
            plt.show()


        if False:
            rlong = self.rGrid
            xlong = np.arange(self.nLevels)
            # import pdb; pdb.set_trace()
            # np.arange(self.nIons+2),rlong,
            # plt.pcolormesh(rlong, xlong, np.log(self.normGrid), vmin = -20, vmax = 1)
            for ii in np.arange(self.nLevels):
                plt.loglog(rlong, self.normGrid[ii], label=ii)
            plt.xlabel('Height')
            plt.legend()
            # plt.colorbar()
            plt.ylabel('Ion')
            plt.title('Equilibrium Ionization, nIons = {}'.format(self.nIons))
            plt.show()

        pass

    def chargeDistributionEq(self, temp, call=None):

        # Create Ngrid
        normSlice = np.zeros(self.nLevels)

        # Create the mathematical series that determines the number in the ground state.
        series = self.groundSeries(temp)

        # Store the total and ground state populations
        normSlice[0] = 1
        normSlice[1] = normSlice[0] / series

        small = -50
        # Determine the populations of the higher states
        for ionNum in np.arange(2, self.nLevels):
            normSlice[ionNum] = normSlice[ionNum - 1] * self.colRate(ionNum - 1, temp) / self.recRate(ionNum, temp)

            # Low density floor
            if normSlice[ionNum] < 10 ** small and call is None: normSlice[ionNum] = 10 ** small

        if call is None:
            return normSlice
        else:
            return -normSlice[call]

    def groundSeries(self, temp):
        '''Solve for the equilibrium ground state'''

        series = 0
        thisList = (np.arange(1, self.nIons) + 1).tolist()
        for i in np.arange(self.nIons):
            # For each necessary term in the series
            term = 1

            for ionNum in thisList:
                # Make that term the multiplication of the remaining ratios
                term *= self.colRate(ionNum - 1, temp) / self.recRate(ionNum, temp)

            series += term

            if len(thisList) > 0: thisList.pop()  # pop the highest valued ratio

        return series

    def findTForm(self, ionNum):
        '''Return the temperature of maximum equilibrium population'''
        results = minimize_scalar(self.chargeDistributionEq, method='bounded', bounds=(1e5, 1e7), args=ionNum)
        temp = results.x
        return temp

    def simulate_all_NLTE(self):
        """Find the NLTE densities as a function of densfac"""

        # Define the grid in the densfac dimension
        self.densPoints = 3# 11  # Must be at least 4, will add "one" below
        dMin = 0.5
        dMax = 12.5
        base = 10
        self.densGrid = np.logspace(np.log(dMin) / np.log(base), np.log(dMax) / np.log(base), self.densPoints,
                                    base=base).tolist()

        # Make sure it does the dd=1 case
        self.densGrid.append(1)
        self.densPoints += 1
        self.densGrid.sort()

        # Define the grid in the R direction
        base = 10
        self.rPoints = 2000
        zmin = 0.0015
        zmax = 75
        self.zEval = np.logspace(np.log(zmin) / np.log(base), np.log(zmax) / np.log(base), self.rPoints,
                                 base=base).tolist()
        self.rEval = [r + 1 for r in self.zEval]

        self.evalR0 = zmin + 1
        self.evalRf = zmax + 1

        # Create arrays to hold everything
        self.bigNLTEGrid = np.zeros((self.densPoints, self.nLevels, self.rPoints))
        self.bigNormGrid = np.zeros_like(self.bigNLTEGrid)

        bar = pb.ProgressBar(self.densPoints, label=self.name.title())
        bar.display()

        # Populate the arrays
        for densfac, dd in zip(self.densGrid, np.arange(self.densPoints)):
            self.bigNLTEGrid[dd], self.bigNormGrid[dd] = self.simulate_one_NLTE(densfac)
            bar.increment()
            bar.display()
            # self.plotGrid(dd)
        print('')

        # Transpose the arrays
        self.bigNLTEGrid = self.bigNLTEGrid.transpose((1, 0, 2))  # nion, densfac, rpoints
        self.bigNormGrid = self.bigNormGrid.transpose((1, 0, 2))

        self.makeInterps()

    def makeInterps(self):
        self.nInterps = []
        self.eqInterps = []

        for ionNum in np.arange(self.nLevels):
            thisState = np.abs(self.bigNLTEGrid[ionNum])
            self.nInterps.append(interp.RectBivariateSpline(self.densGrid, self.rEval, thisState))  # 1/cm^3
            eqState = np.abs(self.nGrid[ionNum])
            self.eqInterps.append(interp.InterpolatedUnivariateSpline(self.rGrid, eqState))

    def getManyN(self, ionNum, densfac, rAxis, eq=False, norm=False):
        """Return the number density of this ion at many heights for given densfac

            eq=True returns the equilibrium values
        """
        if eq:
            actual = np.abs(self.eqInterps[ionNum](rAxis)) * densfac
        else:
            dAxis = np.ones_like(rAxis) * densfac
            actual = np.abs(self.nInterps[ionNum](dAxis, rAxis, grid=False))
        actual[actual < self.minDens] = self.minDens

        # Make sure you aren't asking for data where there isn't any
        axarray = np.asarray(rAxis)
        dmax = np.max(axarray)
        dmin = np.min(axarray)

        if dmax > self.evalRf or dmin < self.evalR0:
            actual[axarray < self.evalR0] = np.NAN
            actual[axarray > self.evalRf] = np.NAN
            print("Warning: Trying to get density data where there is none.")


        if norm:
            total = self.getManyN(0, densfac, rAxis, eq, norm=False)
            actual /= total

        return actual  # Number density 1/cm^3 or unitless if Norm

    def getN(self, ionNum, densfac, rx, eq=False):
        """Return the number density of this ion at this height and densfac"""

        if eq:
            actual = np.abs(self.eqInterps[ionNum](rx, grid=False))
        else:
            actual = np.abs(self.nInterps[ionNum](densfac, rx, grid=False))
        return max(actual, self.minDens)  # Number density 1/cm^3

    def plotGrid(self, densfac=1.0):
        """Plots the results of the NLTE Calculation with the Equilibrium Calculation"""
        doNorm = True
        # Set up evaluation Axis
        nRaxis = 2000
        base = 10
        zmin = 0.011
        zmax = 50
        zGrid = np.logspace(np.log(zmin) / np.log(base), np.log(zmax) / np.log(base), nRaxis,
                            base=base).tolist()
        rGrid = [z + 1 for z in zGrid]

        # Prep the color cycler
        colors = ['k', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9']
        colorcycler = cycle(colors)
        lw = 2

        if self.name in {'n'}: return

        fig, ax = plt.subplots()
        fig.set_size_inches(5,5.5)

        zepDens = [densfac * self.abundance * self.env.interp_rho(rx) / self.env.mP for rx in rGrid]
        clr = next(colorcycler)
        # plt.loglog(zGrid, zepDens, c=clr, ls='-', label="ZephyRho*Abund/mP")
        heights = []
        for nn in np.arange(self.nLevels):
            if nn in [0]: continue
            clr = next(colorcycler)

            thisDens = self.getManyN(nn, densfac, rGrid, eq=False, norm=doNorm)
            equilDens = self.getManyN(nn, densfac, rGrid, eq=True, norm=doNorm)

            ax.semilogx(zGrid, np.log10(thisDens), c=clr, lw=lw, label=nn)
            ax.semilogx(zGrid, np.log10(equilDens), c=clr, ls='--')

            xx = zGrid[-1]*1.1
            yy = np.log10(equilDens[-1])
            if nn in [8]: yy -= 0.75
            ax.annotate(nn, xy=(xx, yy), textcoords='data', color=clr)

            # Find the freezing heights
            xloc, value = self.env.findfreeze(rGrid, thisDens)
            # ax.scatter(xloc, np.log10(value), c=clr)

            if xloc < 4: heights.append(xloc)
            else: xloc = np.nan

            # print('{}_{}: {:0.3}'.format(self.name.title(), nn, xloc))

            #  Ratio Plot
            if False:
                plt.figure()
                rats = thisDens/equilDens
                plt.loglog(zGrid,rats)
                plt.title("Ratio of Fancy/Equilibrium")

        # Plot formatting
        if doNorm: plt.ylabel('$log_{{10}}$(Ion Fraction for {})'.format(self.name.title()))
        else: plt.ylabel('Density')
        # plt.ylabel('Density {}'.format('' if doNorm else '(1/cm^3)'))
        # plt.title(self.name)
        # plt.title("Charge states of {}, ExpansionFactor = {}".format(self.name.title(),useExpansion))
        plt.ylim(-28,1)
        plt.xlim([10**-2.1, 10**2])
        self.env.solarAxis(ax)
        plt.tight_layout()

        plt.show(True)

        ## Print out the freezing heights data
        if False:
            print(self.name.title())
            min = np.min(heights)
            max = np.max(heights)
            print('Mean: {:0.3}, Range: ({:0.3} - {:0.3}), {:0.3}\n'.format(np.mean(heights), min, max, max-min))



    def plotGridRaw(self, dd=2):
        """Plots the results of the NLTE Calculation with the Equilibrium Calculation"""
        doPlot = True
        doNorm = False

        if doNorm:
            big = self.bigNormGrid[:, dd]
            equil = self.normGrid
        else:
            big = self.bigNLTEGrid[:, dd]
            equil = self.nGrid

        # neGrid = self.bigNLTEGrid[dd]
        # neGrid[0, :] = 0
        # neGrid[0, :] = np.sum(neGrid, axis=0)

        ##Normalize the Normgrid
        # big = neGrid / neGrid[0, :]

        colors = ['k', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9']
        colorcycler = cycle(colors)
        # import pdb; pdb.set_trace()

        lw = 2
        if doPlot:
            plt.figure()
            for nn in np.arange(self.nLevels):

                clr = next(colorcycler)

                # Plot NLTE Calculation

                toPlot = big[nn]
                positive = toPlot.copy()
                negative = -toPlot.copy()
                positive[positive < 0] = np.nan
                negative[negative < 0] = np.nan

                plt.loglog(self.zEval, positive, c=clr, marker='o', lw=lw, label=nn)
                plt.loglog(self.zEval, negative, c=clr, marker='x', lw=lw, label=nn)
                # Plot equilibrium Calculation
                plt.loglog(self.zGrid, equil[nn] * self.densGrid[dd], c=clr, ls=':', label=nn)

                try:
                    plt.axvline(self.startHeights[nn], c=clr)
                except:
                    pass

            # plt.pcolormesh((self.bigGrid[dd]))#, vmin = -20, vmax = 1)
            # print(big[0,-1])
            plt.legend(loc="upper left", bbox_to_anchor=(1, 1))
            plt.xlabel('Height')
            plt.ylabel('Density {}'.format('' if doNorm else '(1/cm^3)'))
            # plt.title(self.name)
            plt.ylim([10 ** -30, 10 ** 1])
            plt.suptitle('NLTE Ionization')
            try:
                plt.title('densfac = {:0.4}, ion: {}'.format(self.densGrid[dd], self.name))
            except:
                plt.title('ion: {}'.format(self.name))
            plt.show()

        pass

    def simulate_one_NLTE(self, densfac):
        """Simulate the NLTE densities at a given densfac"""

        self.createInitialGrid(densfac)

        # Perform the actual integration
        # neGrid, normGrid, rAxis = self.manualIonIntegrate()
        neGrid, normGrid = self.stiffIntegrator()  # 1/cm^3, unitless

        return neGrid, normGrid  # , rAxis

    def createInitialGrid(self, densfac):
        """Mostly just creates dudr at this point"""

        # Pull in the equilibrium calculation and adjust density (Initial Conditions)
        self.thisDensfac = densfac
        self.neGrid = copy.deepcopy(self.nGrid * densfac)

        # Calculate the rho and wind velocities on the rGrid
        self.rhoGrid = [self.env.interp_rho(rx) * densfac for rx in self.rGrid]  # g/cm^3
        self.uGrid = [self.env.interp_wind(rx) / densfac ** 0.5 for rx in self.rGrid]  # cm/s

        # Calculate the Derivative of the wind speed
        self.dudrAll = np.gradient(np.asarray(self.uGrid), np.asarray(self.rGrid) * self.env.r_Cm)

        # Calculate the Super Radial Expansion factor and Derivative
        self.sfGrid = [self.env.getAreaF_raw(rx) for rx in self.rGrid]
        self.dfdrAll = np.gradient(np.asarray(self.sfGrid), np.asarray(self.rGrid) * self.env.r_Cm)

        if False:
            fig, (ax2) = plt.subplots(1, 1, True)
            ax1 = ax2.twinx()
            # ax2.set_ylabel('Density', color='r')
            ax2.tick_params('y', colors='r')
            ax1.tick_params('y', colors='b')
            ax2.loglog(self.zGrid, self.dfdrAll, 'r', label="Derivative")
            ax1.loglog(self.zGrid, [s for s in self.sfGrid], label="SuperRadial")

            ax2.set_ylabel("Derivative")
            ax1.set_ylabel("SuperRadial Expansion")
            plt.xlabel("Z")
            plt.show()

        # Plot the inputs
        if False:
            plt.loglog(self.rGrid, self.tGrid, label='T')
            plt.loglog(self.rGrid, self.uGrid, label='U')
            # plt.loglog(self.rGrid, self.rhoGrid, label=r'$\rho$')
            plt.loglog(self.rGrid, self.nGrid[0], label='N0_{}'.format(self.ion['eString']))
            plt.legend()
            plt.show()

        # This just prints the function and derivative
        if False:
            fig, ax = plt.subplots()
            line1 = ax.loglog(self.zGrid, dudrAll, 'ob', label='Derivative')
            ax2 = ax.twinx()
            line2 = ax2.loglog(self.zGrid, self.uGrid, 'or', label="Function")
            lns = line1 + line2
            labs = [l.get_label() for l in lns]
            ax.legend(lns, labs, loc=8)
            plt.show()

    def stiffIntegrator(self):
        """A more advanced approach to the problem"""

        # Pull in the initial conditions
        neGrid = self.neGrid  # 1/cm^3
        cGrid = np.zeros_like(neGrid)
        eventGrid = np.zeros_like(neGrid)
        normGrid = copy.deepcopy(self.normGrid)

        # Define Range of Integration
        r0 = self.evalR0
        rf = self.evalRf

        ind = self.env.find_nearest(np.asarray(self.rGrid), r0) - 1
        r00 = self.rGrid[ind] * self.env.r_Cm
        rf0 = rf * self.env.r_Cm

        r_eval = np.asarray(self.rEval) * self.env.r_Cm

        # Get the initial densities
        nl = neGrid[:, ind]  # 1/cm^3
        nl = np.append(nl, 0)  # make there be a zero density higher state

        # Integrate!
        method = 'Radau'  # 'BDF', 'LSODA', 'RK45'
        atol = 1e-36

        results = integrate.solve_ivp(self.ionDerivativeR, (r00, rf0), nl, method=method, atol=atol, t_eval=r_eval)

        # rAxis = results.t
        neGrid = np.abs(results.y)

        # Make the n0 row actually be the sum of the other rows
        neGrid[0, :] = 0
        neGrid[0, :] = np.sum(neGrid, axis=0)

        # Remove the fake upper level row
        neGrid = np.delete(neGrid, self.nLevels, axis=0)

        # Normalize the Normgrid
        normGrid = neGrid / neGrid[0, :]

        # Create the z axis output
        # zAxis = rAxis/self.env.r_Cm - 1

        return neGrid, normGrid  # , zAxis (Units: number density, unitless)

    def ionDerivativeR(self, r, nl):
        """The RHS function for the ionization balance"""

        # Convert inputs
        rx = r / self.env.r_Cm
        RHS = np.zeros_like(nl)

        # Density
        densfac = self.thisDensfac
        rho = self.env.interp_rho(rx) * densfac  # g/cm^3 #TODO So is this rho correct then?
        nE = rho / self.env.mP  # num/cm^3 #This assumes hydrogen is fully ionized

        # Solar Wind
        ur = self.env.interp_wind(rx) / densfac ** 0.5
        dudr = self.env.interp(self.rGrid, self.dudrAll, rx)

        # Expansion Factor
        f = self.env.getAreaF_raw(rx)
        dfdr = self.env.interp(self.rGrid, self.dfdrAll, rx)

        # Temperature
        T = self.env.interp_T(rx)

        for ionNum in np.arange(1, self.nLevels):
            # Ionization and Recombination
            C1 = nl[ionNum - 1] * self.colRate(ionNum - 1, T)
            C2 = nl[ionNum + 1] * self.recRate(ionNum + 1, T)
            C3 = - nl[ionNum] * (self.colRate(ionNum, T))
            C4 = - nl[ionNum] * (self.recRate(ionNum, T))

            I = nE * (C1 + C2 + C3 + C4)
            # 1/cm^3 * cm^3/s = 1/s

            RHS[ionNum] += I / ur  # 1/cm^3 * 1/s * s/cm = 1/cm^4
            RHS[ionNum] -= 2 * nl[ionNum] / r  # 1/cm^3 / cm = 1/cm^4
            RHS[ionNum] -= dudr * nl[ionNum] / ur  # 1/cm^3 * s/cm * cm/s / cm = 1/cm^4
            RHS[ionNum] -= dfdr * nl[ionNum] / f  # New term to account for supperradial expansion


            # RHS =  nE*C/ur - 2*n[ionNum]/r  - n[ionNum]/ur*du/dr

        return RHS

    def recRate(self, ionNum, temp):
        """Return R, the recombination from I to I-1"""
        if not 2 <= ionNum <= self.nIons: return 0
        return self.recombList[ionNum](temp)  # cm^3/s

    def colRate(self, ionNum, temp):
        """Return C, the collision rate from I to I+1"""
        if not 1 <= ionNum < self.nIons: return 0
        return self.collisList[ionNum](temp)  # cm^3/s

    def nRead(self, ionNum, r):
        return self.env.interp(self.rGrid, self.nGrid[ionNum], r)

    def loadRateLists(self):
        '''Load in the recombination and collision rates for all of the ions of this element'''
        # self.ratList = []
        self.recombList = []
        self.collisList = []
        self.ionArray = np.arange(self.nLevels)

        self.colors = ['C0', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9']
        colorcycler = cycle(self.colors)

        for ionNum in self.ionArray:
            # Load Recombination Rate out of this ion
            if not 2 <= ionNum <= self.nIons:
                self.recombList.append(0)
            else:
                T_array, thisRecomb = self.env.cLoadOneRecombRate(self.ion['eString'], ionNum)
                recombFunc = partial(self.env.interp, T_array, thisRecomb)
                self.recombList.append(recombFunc)  # cm^3/s

            # Load Collison Rate out of this ion
            if not 1 <= ionNum < self.nIons:
                self.collisList.append(0)
            else:
                T_array, thisCollis = self.env.cLoadOneCollisRate(self.ion['eNum'], ionNum)
                collisFunc = partial(self.env.interp, T_array, thisCollis)
                self.collisList.append(collisFunc)  # cm^3/s

            if False:
                # Plot all the recombination and collision times
                clr = next(colorcycler)
                plt.loglog(T_array, thisRecomb, clr + '-', label='recomb_{}'.format(ionNum))
                plt.loglog(T_array, thisCollis, clr + '--', label='collis_{}'.format(ionNum))
                plt.title(ion['ionString'])
                plt.legend()
                plt.xlabel('Temperature')
                plt.ylabel('Rate')
        # plt.show()
        # print(self.ionArray.tolist())
        # print(self.recombList)
        # print(self.collisList)

        # import pdb; pdb.set_trace()
        return

    def plotAll(self):

        plt.figure()

        absolute = False
        vsHeight = True

        if absolute:
            plt.title('{}, absolute'.format(self.ion['eString']))
            grid = self.nGrid
        else:
            plt.title('{}, relative'.format(self.ion['eString']))
            grid = self.normGrid

        if vsHeight:
            plt.xlabel('Height')
            absiss = self.rGrid
            plt.ylim([1e-8, 2])
        else:
            plt.xlabel('Temperature')
            absiss = self.tGrid
            plt.ylim([1e-3, 2])

        plt.ylabel('Population')
        for ionNum in np.arange(self.nLevels):
            plt.plot(absiss, (grid[ionNum]), label=ionNum)
        plt.legend()

        plt.xscale('log')
        plt.yscale('log')
        plt.show()

    ###Depricated
    def manualIonIntegrate(self):
        """A forward Euler Approach to the Problem"""

        # Pull in the initial conditions
        neGrid = self.neGrid
        cGrid = np.zeros_like(neGrid)
        eventGrid = np.zeros_like(neGrid)
        normGrid = copy.deepcopy(self.normGrid)

        # Do the Math
        for writeEnabled in [False, True]:
            if writeEnabled: self.startHeights = self.findStartHeights(eventGrid)
            for temp, rr, ur, jj in zip(self.tGrid, self.rGrid, self.uGrid, np.arange(self.nRGrid)):
                if jj < 1: continue  # Skip at least the lowest column
                r = rr * self.env.r_Cm  # cm
                z = rr - 1

                dr = (self.rGrid[jj] - self.rGrid[jj - 1]) * self.env.r_Cm  # change in height    #cm
                dudr = self.dudrAll[jj]

                # h = (self.rGrid[jj] - self.rGrid[jj-1]) * self.env.r_Cm #change in height    #cm
                # du = self.uGrid[jj] - self.uGrid[jj-1] #change in wind over that height #cm/s
                # dudr1 = du/h

                rho = self.rhoGrid[jj - 1]  # g/cm^3
                nE = rho / self.env.mP  # num/cm^3

                # Get the densities of all ions at the last height
                nl = neGrid[:, jj - 1]  # 1/cm^3

                nl = np.append(nl, 0)  # make there be a zero density higher state

                for ionNum in np.arange(1, self.nLevels):
                    # For each ion

                    # Ionization and Recombination
                    C1 = nl[ionNum - 1] * self.colRate(ionNum - 1, self.tGrid[jj - 1])
                    C2 = nl[ionNum + 1] * self.recRate(ionNum + 1, self.tGrid[jj - 1])
                    C3 = - nl[ionNum] * (self.colRate(ionNum, self.tGrid[jj - 1]))
                    C4 = - nl[ionNum] * (self.recRate(ionNum, self.tGrid[jj - 1]))

                    C = C1 + C2 + C3 + C4
                    # 1/cm^3 * cm^3/s = 1/s

                    if not writeEnabled:
                        pf = nE / ur
                        CR1 = np.abs(pf * C1)
                        CR2 = np.abs(pf * C2)
                        CR3 = np.abs(pf * C3)
                        CR4 = np.abs(pf * C4)
                        collisMax = max(CR1, CR2, CR3, CR4)

                        GR1 = np.abs(2 * nl[ionNum] / r)
                        GR2 = np.abs(nl[ionNum] / ur * dudr)
                        geoMax = max(GR1, GR2)

                        eventGrid[ionNum, jj] = collisMax / geoMax
                        cGrid[ionNum, jj] = dudr
                        continue

                    if z <= self.startHeights[ionNum]: continue

                    RHS = 0
                    RHS += nE * C / ur  # 1/cm^3 * 1/s * s/cm = 1/cm^4
                    RHS -= 2 * nl[ionNum] / r  # 1/cm^3 / cm = 1/cm^4
                    RHS -= nl[ionNum] / ur * dudr  # 1/cm^3 * s/cm * cm/s / cm = 1/cm^4

                    # RHS =  nE*C/ur - 2*n[ionNum]/r  - n[ionNum]/ur*du/dr

                    change = dr * RHS  # 1/cm^3
                    neGrid[ionNum, jj] = nl[ionNum] + change
                    normGrid[ionNum, jj] = neGrid[ionNum, jj] / neGrid[0, jj]

        # Plot whatever is in the cGrid
        if False:
            self.cName = "collis/geo"
            plt.figure()
            colorcycler = cycle(self.colors)
            for ii in self.ionArray.tolist():
                # if ii < 5: continue
                clr = next(colorcycler)
                plt.loglog(self.zGrid, cGrid[ii], 'o-' + clr, label=ii)
                plt.axvline(self.startHeights[ii], c=clr, alpha=0.7)

                # thismax = np.abs(np.mean(cGrid)) #np.max(np.abs(cGrid[ii]))
                # plt.loglog(self.zGrid, normGrid[ii], 'o'+clr, label=ii)
                # plt.semilogx(self.zGrid, cGrid[ii]/thismax, clr, label = ii)
            # print(cGrid[-1])
            plt.legend()
            plt.ylabel('C')
            plt.axhline(self.cutThreshold)
            plt.xlabel('height')
            plt.title(self.cName)
            plt.show()

        return neGrid, normGrid, self.zGrid

    def findStartHeights(self, eventGrid):
        startHeights = np.zeros_like(eventGrid[:, 0])
        self.cutThreshold = 300

        for ionNum in np.arange(1, self.nLevels):
            inds = np.argwhere(eventGrid[ionNum] > self.cutThreshold)
            lastInd = int(inds[-1])
            startHeights[ionNum] = self.zGrid[lastInd]

        # print(startHeights)
        return startHeights

    def particleTimes(self, ionNum, jj, useMax=False):
        """Determine the Collision and the Expansion time at a Radius"""

        t_E = self.expansionTime(jj)  # Seconds
        t_C = self.collisionTime(jj, ionNum, useMax)  # Seconds

        return t_C, t_E

    def expansionTime(self, jj):
        """Return the Expansion Timescale"""

        # Aquire relevant parameters
        rho = self.rhoGrid[jj]  # g/cm^3
        wind = self.uGrid[jj]  # cm/s

        # Finite Difference
        rs_cm = self.env.r_Mm * 10 ** 8  # cm/solar radius
        h = (self.rGrid[jj] - self.rGrid[jj - 1]) * rs_cm  # cm

        var = self.rhoGrid  # g/cm^3
        try:
            drhodr = (var[jj + 1] - var[jj - 1]) / (2 * h)  # g/cm^4
        except IndexError:
            drhodr = (var[jj] - var[jj - 1]) / h  # g/cm^4

        # Calculate Timescale
        t_E = np.abs((rho / wind) * (1 / drhodr))  # seconds

        return t_E  # Seconds

    def collisionTime(self, jj, ionNum, useMax=False):
        """Return the collisional equilibrium timescale"""

        # Aquire relevant parameters
        rho = self.rhoGrid[jj]  # g/cm^3
        nE = rho / self.env.mP  # num/cm^3
        T = self.tGrid[jj]  # Kelvin

        # Find rates to state below
        recomb1 = self.recRate(ionNum, T)  # cm^3/s
        collis1 = self.colRate(ionNum - 1, T)  # cm^3/s

        # Find rates to state above
        recomb2 = self.recRate(ionNum + 1, T)  # cm^3/s
        collis2 = self.colRate(ionNum, T)  # cm^3/s

        # Find times for both rates
        t_C1 = 1 / (nE * (recomb1 + collis1))  # Collisional Time in s
        t_C2 = 1 / (nE * (recomb2 + collis2))  # Collisional Time in s

        slowest = max(recomb1, collis1, recomb2, collis2)
        t_C_slow = 1 / (nE * slowest)

        # t_C_slow = max(t_C1, t_C2)

        # Use only the appropriate times
        if useMax:
            t_C = t_C_slow
        else:
            if ionNum < 2:
                t_C = t_C2
            elif ionNum >= self.nIons:
                t_C = t_C1
            else:
                t_C = np.sqrt(t_C1 * t_C2)

        return t_C

    def plotTimes(self):
        plt.figure()
        for ionNum in np.arange(1, self.nLevels):
            col = []
            exp = []
            for jj in np.arange(self.nRGrid):
                t_C, t_E = self.particleTimes(ionNum, jj)
                col.append(t_C)
                exp.append(t_E)

            # plt.loglog(self.rGrid, col)
            # plt.loglog(self.rGrid, exp, 'b')
            plt.loglog(self.zGrid, [e / c for c, e in zip(col, exp)])
            plt.ylabel('Seconds')
            plt.xlabel('Solar Radii')
            plt.axhline(10 ** 2, ls=':', c='k')
        plt.show()


####################################################################
##                           Simulation                           ##
####################################################################

## Level 0: Simulates physical properties at a given coordinate
class simpoint:
    g_Bmin = 3.8905410
    ID = 0

    wavesVsR = True
    plotIncidentArray=False

    # Level 0: Simulates physical properties at a given coordinate
    def __init__(self, cPos=[0.1, 0.1, 1.5], grid=None, env=None, findT=True, pbar=None, copyPoint=None):
        # Inputs
        self.didIonList = []
        self.grid = grid
        self.env = env
        self.ions = copy.deepcopy(self.env.getIons(self.env.maxIons))

        if findT is None:
            self.findT = self.grid.findT
        else:
            self.findT = findT

        self.loadParams(copyPoint)

        self.relocate(cPos)

        # self.removeEnv()

        if pbar is not None:
            pbar.increment()
            pbar.display()

    def relocate(self, cPos, t=0):
        self.cPos = cPos
        self.pPos = self.cart2sph(self.cPos)
        self.rx = self.r2rx(self.pPos[0])
        self.zx = self.rx - 1
        self.maxInt = 0
        self.totalInt = 0
        # Initialization
        self.findTemp()
        self.findFootB()
        self.findDensity()
        self.findTwave()
        self.__streamInit()
        self.__findFluxAngle()
        self.findSpeeds(t)
        self.findUrProj()
        # self.findDPB()

        return self

    def loadParams(self, copyPoint):
        if copyPoint is None:
            self.useWaves = simpoint.g_useWaves
            self.useWind = simpoint.g_useWind
            self.Bmin = simpoint.g_Bmin

            self.bWasOn = self.useB
            self.waveWasOn = self.useWaves
            self.windWasOn = self.useWind
        else:
            self.useWaves = copyPoint.useWaves
            self.useWind = copyPoint.useWind
            self.Bmin = copyPoint.Bmin

    def removeEnv(self):
        del self.env

    ## Temperature ######################################################################
    def findTemp(self):
        self.T = self.interp_rx_dat_log(self.env.T_raw)  # Lowest Temp: 1200

    ## Magnets ##########################################################################
    def findFootB(self):
        # Find B
        self.__findfoot_Pos()
        x = self.foot_cPos[0]
        y = self.foot_cPos[1]

        if self.useB:
            self.footB = self.env.interp_map(self.env.BMAPs, self.grid.envInd, x, y)
        else:
            self.footB = 0

    def __findfoot_Pos(self):
        # Find the footpoint of the field line
        self.f = self.env.getAreaF_smooth(self.rx)
        theta0_edge = self.env.theta0 * np.pi / 180.
        theta_edge = np.arccos(1. - self.f + self.f * np.cos(theta0_edge))
        edge_frac = theta_edge / theta0_edge
        coLat = self.pPos[1] / edge_frac
        self.foot_pPos = [self.env.rstar + 1e-2, coLat, self.pPos[2]]
        self.foot_cPos = self.sph2cart(self.foot_pPos)

    def __findStreamIndex(self):
        x = self.foot_cPos[0]
        y = self.foot_cPos[1]
        self.streamIndex = self.env.interp_map(self.env.BLABELs, self.grid.envInd, x, y)
        # self.streamIndex = self.env.label_im[self.find_nearest(self.env.BMap_x, x)][self.find_nearest(self.env.BMap_y, y)]

    ## Density ##########################################################################
    def findDensity(self):
        # Find the densities of the grid point
        self.densfac = self.__findDensFac()
        self.rho = self.__findRho(self.densfac)  # Total density
        self.nE = self.rho / self.env.mP  # electron number density

        for ion in self.ions:
            ion['N'] = self.env.getDensity(ion, self.densfac, self.rx)

    def __findDensFac(self):
        # Find the density factor
        Bmin = self.Bmin
        Bmax = 50

        if self.footB < Bmin:
            self.B0 = Bmin
        elif self.footB > Bmax:
            self.B0 = Bmax
        else:
            self.B0 = self.footB
        dinfty = (self.B0 / 15) ** 1.18

        if False:  # Plot the density factor lines
            xx = np.linspace(0, 3, 100)
            dd = np.linspace(0, 20, 5)
            for d in dd:
                plt.plot(xx + 1, self.__densFunc(d, xx), label="{} G".format(d))
            plt.xlabel('r/$R_\odot$')
            plt.ylabel('$D_r$')
            plt.legend()
            plt.show()

        if self.useB:
            return self.__densFunc(dinfty, self.zx)
        else:
            return 1

    def __densFunc(self, d, x):
        return (0.3334 + (d - 0.3334) * 0.5 * (1. + np.tanh((x - 0.37) / 0.26))) * 3

    def __findRho(self, densfac=1):
        return self.env.interp_rho(self.rx) * densfac
        # return self.interp_rx_dat_log(self.env.rho_raw) * densfac

    ## pB stuff ##########################################################################

    def findDPBold(self):
        imp = self.cPos[2]
        r = self.pPos[0]
        u = 0.63
        R_sun = 1
        sigmaT = 5e-12  # 6.65E-25 #

        eta = np.arcsin(R_sun / r)
        mu = np.cos(eta)

        f = mu ** 2 / np.sqrt(1 - mu ** 2) * np.log(mu / (1 + np.sqrt(1 - mu ** 2)))
        A = mu - mu ** 3
        B = 1 / 4 - (3 / 8) * mu ** 2 + f / 2 * ((3 / 4) * mu ** 2 - 1)

        self.dPB = 3 / 16 * sigmaT * self.nE * (imp / r) ** 2 * ((1 - u) * A + u * B) / (1 - u / 3)

        return self.dPB

    def findDPB(self):
        imp = self.cPos[2]
        x = self.cPos[0]
        r = self.pPos[0]
        u = 0.63
        R_sun = 1
        sigmaT = 7.95E-26  # cm^2
        I0 = 2.49E10  # erg/ (cm^2 s sr)

        Tau = np.arctan2(x, r)
        Omega = np.arcsin(R_sun / r)

        A = np.cos(Omega) * np.sin(Omega) ** 2

        B = -1 / 8 * (1 - 3 * np.sin(Omega) ** 2 - np.cos(Omega) ** 2 / np.sin(Omega) * (
                1 + 3 * np.sin(Omega) ** 2) * np.log((1 + np.sin(Omega)) / np.cos(Omega)))

        self.dPB = 0.5 * np.pi * sigmaT * I0 * self.nE * np.cos(Tau) ** 2 * ((1 - u) * A + u * B)

        return self.dPB

    ## Radiative Transfer ################################################################

    def getProfiles(self, lenCm=1, ions=None):
        self.lenCm = lenCm
        if ions is None: ions = self.ions
        else: ions = [self.ions[ion['cNum']] for ion in ions]

        profiles = []
        for ion in ions:
            profileC = self.collisionalProfile(ion)
            profileR = self.resonantProfile(ion)
            profiles.append([profileC, profileR])
        self.env.plotMore = False
        return profiles

    def collisionalProfile(self, ion):
        """Generate the collisionally excited line profile"""
        lam0 = ion['lam00']  # Angstroms
        vTh = np.sqrt(2 * self.env.KB * self.T / ion['mIon'])  # cm/s
        deltaLam = lam0 * vTh / self.env.c  # ang
        lamLos = lam0 * self.vLOS / self.env.c  # ang

        expblock = (ion['lamAx'] - lam0 - lamLos) / (deltaLam)  # unitless

        lamPhi = 1 / (deltaLam * self.env.rtPi) * np.exp(-expblock * expblock)  # 1/ang

        const = self.env.hergs * self.env.c / self.env.ang2cm(lam0) / 4 / np.pi  # ergs s

        profileC = self.lenCm * const * self.nE * ion['N'] * self.env.findQt(ion,
                                                                       self.T) * lamPhi  # ergs /s /sr /cm^2 /ang ;  Q=[cm^3/s^2/sr]

        ion['dimmingFactor'] = np.exp(-(self.ur/vTh)**2)
        ion['profileC'] = profileC  # ergs / (s cm^2 sr angstrom)
        ion['totalIntC'] = np.sum(profileC)
        ion['Cmax'] = np.max(profileC)

        return profileC

    def resonantProfile(self, ion):
        """Generate the resonantly scattered line profile"""

        nuAxPrime, nuI0Array = self.rIncidentArray(ion)
        profileR = self.rProfile(ion, nuAxPrime, nuI0Array)

        ## Store values
        ion['profileR'] = profileR
        ion['totalIntR'] = np.sum(ion['profileR'])
        ion['Rmax'] = np.max(profileR)

        return ion['profileR']

    def rIncidentArray(self, ion):
        """ Create the Incident Light Array """

        if self.doChop:
            if ion['cNum'] == 2 and self.keepPump:
                lamAxPrime, I0array = self.makePumpArray(ion)
            else:
                lamAxPrime, I0array = self.makeChopArray(ion)
        else:
            lamAxPrime, I0array = self.makeFullArray(ion)

        if ion['cNum'] == 2 and self.plotIncidentArray:
            self.doPlotIncidentArray(ion)

        # Convert from lam to nu
        nuAxPrime = self.env.lamAx2nuAx(lamAxPrime)  # Hz
        nuI0Array = self.env.lam2nuI0(I0array, lamAxPrime)  # ergs/s/cm^2/sr/Hz

        return nuAxPrime, nuI0Array

    def makePumpArray(self, ion):
        """Make the incident light for the O6 line, keeping pumping lines"""
        lamAxPrime, I0array = self.makeFullArray(ion)
        I0array = self.chop1037(I0array)
        return lamAxPrime, I0array

    def makeFullArray(self, ion):
        """Create a full incident array"""
        sigma = 6
        rezPerAng = 150
        minRez = 60
        lamCenter, deltaLam = self.findArrayLimits(ion)
        lowLamNorm = lamCenter - sigma * deltaLam  # New limits for this point
        highLamNorm = ion['lam00'] + sigma * deltaLam  # New limits for this point
        throwNorm = highLamNorm - lowLamNorm  # total width in angstroms
        longRez = int(throwNorm * rezPerAng)
        rez = np.max((longRez, minRez))
        lamAxPrimeNorm = np.linspace(lowLamNorm, highLamNorm, rez)
        I0arrayNorm = [self.env.interp(ion['lamAxPrime'], ion['I0array'], ll) for ll in lamAxPrimeNorm]
        return lamAxPrimeNorm, I0arrayNorm

    def makeChopArray(self, ion):
        """Create a chopped incident array"""
        sigma = 3
        rezPerAng = 150
        minRez = 60
        lamCenter, deltaLam = self.findArrayLimits(ion)
        lowLamChop = ion['lam00'] - sigma * deltaLam  # New limits for this point
        highLamChop = ion['lam00'] + sigma * deltaLam  # New limits for this point
        throwChop = highLamChop - lowLamChop  # total width in angstroms
        longRez = int(throwChop * rezPerAng)
        rez = np.max((longRez, minRez))
        lamAxPrimeChop = np.linspace(lowLamChop, highLamChop, rez)
        I0arrayChop = [self.env.interp(ion['lamAxPrime'], ion['I0array'], ll) for ll in lamAxPrimeChop]
        return lamAxPrimeChop, I0arrayChop

    def findArrayLimits(self, ion):
        """Determine the limits for the incident array"""
        # Thermal Velocity
        Vth = np.sqrt(2 * self.env.KB * self.T / ion['mIon'])  # cm/s

        # Find the necessary limits for this redshift
        lamShift = ion['lam00'] * self.ur / self.env.c  # Redshift of this point
        lamCenter = ion['lam00'] - lamShift  # Center of this points spectrum
        deltaLam = ion['lam00'] * Vth / self.env.c  # Width of the line here
        return lamCenter, deltaLam

    def chop1037(self, I0array):
        """Cut the continuum out of the 1037 line"""
        cutoff = 10
        I0array = np.asarray(I0array)
        I0array[I0array < cutoff] = 0
        return I0array.tolist()

    def doPlotIncidentArray(self, ion):
        """Plot the various types of incident array"""
        fig, ax = plt.subplots()
        ax.plot(*self.makeFullArray(ion), 'b-', label='Full Range', lw=2)
        ax.plot(*self.makePumpArray(ion), 'r-', label='Pumping Lines', lw=2.5)
        ax.plot(*self.makeChopArray(ion), 'c-', label='Line Core', lw=3)
        ax.legend()
        ax.set_ylabel("Intensity")
        ax.set_xlabel(r"Wavelength ($\AA$)")
        ax.set_title("Incident Spectrum from Photosphere (SUMER)")
        plt.tight_layout()
        plt.show(True)

    def rProfile(self, ion, nuAxPrime, nuI0Array):
        """ Calculate Resonant Profile """

        # Thermal Velocity
        Vth = np.sqrt(2 * self.env.KB * self.T / ion['mIon'])  # cm/s

        # Geometric factors
        ro = np.sqrt(self.cPos[0] * self.cPos[0] + self.cPos[1] * self.cPos[1]) * np.sign(self.vLOS)
        Theta = np.arccos(ro / self.pPos[0])
        alpha = np.cos(Theta)
        beta = np.sin(Theta)
        inv_beta = 1 / beta

        # Other scalar calculations
        nu0 = ion['nu0']
        Nion = ion['N']
        dNu = np.abs(np.mean(np.diff(nuAxPrime)))  # Hz
        deltaNu = nu0 * Vth / self.env.c  # 1/s
        scalarFactor = self.lenCm * self.env.hergs * nu0 / (4 * np.pi) * ion[
            'B12'] * Nion * dNu * self.findSunSolidAngle()  # hz*hz

        g1 = (1 - ion['E1'] / 4) + 3 / 4 * ion['E1'] * alpha * alpha  # new phase function

        Rfactor = g1 / (np.pi * beta * deltaNu * deltaNu)  # 1/(hz*hz)
        preFactor = scalarFactor * Rfactor  # unitless

        # Normed LOS and radial velocities
        los_Vth = self.vLOS / Vth
        rad_Vth = self.ur / Vth

        # Create a column and a row vector
        zeta = (ion['nuAx'] - nu0) / deltaNu - los_Vth
        zetaTall = zeta[np.newaxis].T
        zetaPrime = (nuAxPrime - nu0) / deltaNu - rad_Vth

        zetaDiffBlock = (zetaTall - alpha * zetaPrime) * inv_beta

        R = self.rKernal(zetaPrime, zetaDiffBlock)

        # Apply that matrix to the incident light profile
        profileRnu = preFactor * np.dot(R, nuI0Array)  # ergs/s/cm^2/sr/Hz

        # Convert from nu back to lam
        profileR = profileRnu * ion['nuAx'] / ion['lamAx']  # ergs/s/cm^2/sr/Angstrom

        return profileR

    def rKernal(self, zetaPrime, zetaDiffBlock):
        # Use the vectors to create a matrix
        exponent = - zetaPrime*zetaPrime - zetaDiffBlock*zetaDiffBlock
        R = np.exp(exponent)
        return R

    def rPlot(self):
        """ Plot the slice being used as incident light """
        stepdown = 0.2

        def gauss_function(x, a, x0, sigma, b):
            return a * np.exp(-(x - x0) ** 2 / (2 * sigma ** 2)) + b

        plotIncident = False

        if plotIncident and self.pPos[0] + stepdown < self.env.lastPos and ion['eString'] == 's':
            self.env.lastPos = self.pPos[0]

            plt.figure()
            plt.axvline(lowLam)
            plt.axvline(highLam)
            plt.axvline(lamCenter)
            plt.title("{}_{}".format(ion['eString'], ion['ionNum']))
            plt.plot(ion['lamAxPrime'], ion['I0array'], label="Full")

            plt.plot(ion['lamAx'], gauss_function(ion['lamAx'], 50, lamCenter, deltaLam, 0))

            plt.plot(lamAxPrime, I0array, '.-', label="Slice")
            ionName = "{}_{}".format(ion['eString'], ion['ionNum'])
            plt.title("{}\nR = {:.3}, X,Z = {:.3}, {:.3}\n radialV = {:.4}".format(ionName, self.pPos[0], self.cPos[0],
                                                                                   self.cPos[2],
                                                                                   self.env.cm2km(radialV)))
            plt.legend()

            if False:
                plt.show()
            else:
                savePath = "../fig/2018/steps"
                plt.savefig("{}/{:.3}.png".format(savePath, self.pPos[0]))
                plt.close()

    def findSunSolidAngle(self):
        """Return the proportion of the sky covered by the sun"""
        return 0.5 * (1 - np.sqrt(1 - (1 / self.rx) ** 2))

    ## Velocity ##########################################################################

    def findSpeeds(self, t=0):
        # Find all of the static velocities

        if self.useWind:
            self.uw = self.__findUw()
        else:
            self.uw = 0
        self.vAlf = self.__findAlf()  # cm/s
        self.vPh = self.__findVPh()  # cm/s

        self.findWaveSpeeds(t)

    def findWaveSpeeds(self, t=0):
        # Find all of the wave velocities

        if self.useWaves:
            self.vRms = self.env.interp_vrms(self.rx)  # cm/s

            if self.wavesVsR:
                self.alfU1 = self.vRms * self.getU1(t)
            else:
                # Just the time method
                self.t1 = t - self.twave + self.alfT1
                self.alfU1 = self.vRms * self.xi1(self.t1)
        else:
            self.alfU1 = 0
            self.vRms = 0

        # Modify the waves based on density
        self.alfU1 = self.alfU1 / self.densfac ** 0.25

        # Rotate the waves and place them in correct coordinates
        uTheta = self.alfU1  # * np.sin(self.alfAngle) + self.alfU2 * np.cos(self.alfAngle)
        uPhi = self.alfU1  # * np.cos(self.alfAngle) - self.alfU2 * np.sin(self.alfAngle)
        pU = [self.uw, uTheta, uPhi]

        pU = self.fluxAngleOffset(pU, self.delta)

        self.updateVelocities(pU)

    def updateVelocities(self, pU):
        self.ur, self.uTheta, self.uPhi = pU
        self.pU = pU
        self.cU = self.__findCU(pU)
        self.ux, self.uy, self.uz = self.cU
        self.vLOS = self.__findVLOS()

    def getU1(self, t):
        # Return the correct wave profile at given time

        if self.zx < 0: return np.nan

        # Set the wave time
        self.t1 = t + self.alfT1

        # Get the wave profile at that time from the 2D function
        U1 = self.interp_R_wave(self.t1)

        # If that doesn't work, do it the time way
        if np.isnan(U1):
            offsetTime = 410.48758
            U1 = self.xi1(self.t1 - self.twave + offsetTime)
        return U1

    def interp_R_wave(self, t):
        """Return the unitless wave profile"""
        if self.zx > self.env.R_zx[-1]: return np.nan
        t_int = int(t % self.env.R_ntime)  # find closest time
        R_Array = self.env.normedV2D[:, t_int]  # extract all heights at that time
        V = self.env.interp(self.env.R_zx, R_Array, self.zx)  # interpolate to exact height
        return V  # unitless

    def xi1(self, t):
        # Returns xi1(t)
        if math.isnan(t):
            return math.nan
        else:
            t_int = int(t % self.env.tmax)
            xi1 = self.env.xi1_raw[t_int]
            xi2 = self.env.xi1_raw[t_int + 1]
            return xi1 + ((t % self.env.tmax) - t_int) * (xi2 - xi1)

    def __findFluxAngle(self):
        dr = 1e-4
        r1 = self.rx
        r2 = r1 + dr

        footTheta = self.foot_pPos[1]

        self.thetar1 = np.arccos(1 - self.env.getAreaF_smooth(r1) * (1 - np.cos(footTheta)))
        self.thetar2 = np.arccos(1 - self.env.getAreaF_smooth(r2) * (1 - np.cos(footTheta)))
        self.dtheta = self.thetar2 - self.thetar1

        self.delta = np.arctan2(r1 * self.dtheta, dr)
        self.dangle = self.pPos[1] + self.delta
        # self.dx = np.cos(self.delta)
        # self.dy = np.sin(self.delta)

    def fluxAngleOffset(self, pU, delta):
        ur = pU[0]
        utheta = pU[1]

        newUr = ur * np.cos(delta) - utheta * np.sin(delta)
        newTheta = utheta * np.cos(delta) + ur * np.sin(delta)

        newPU = [newUr, newTheta, pU[2]]
        return newPU

    def findUrProj(self):

        uw = self.__findUw(False)
        vRms = self.env.interp_vrms(self.rx)
        weight = self.__findRho()**self.env.weightPower

        self.urProj =  weight * (np.sin(self.dangle) *  uw ) ** 2
        self.rmsProj = weight * (np.cos(self.dangle) * vRms) ** 2
        self.temProj = weight * self.T

    def __streamInit(self):
        self.__findStreamIndex()
        self.env.streamRand.seed(int(self.streamIndex))
        thisRand = self.env.streamRand.random_sample(3)

        if self.wavesVsR:
            last1 = self.env.R_ntime
            last2 = last1
        else:
            last1 = self.env.tmax
            last2 = last1

        self.alfT1 = int(thisRand[0] * last1)
        self.alfT2 = int(thisRand[1] * last2)
        self.alfAngle = thisRand[2] * 2 * np.pi

    def __findUw(self, useDens=True):
        # Wind Velocity
        densfac = self.densfac if useDens else 1
        return self.windFactor * self.env.interp_wind(self.rx) / densfac ** 0.5

    def __findAlf(self):
        # Alfven Velocity
        # return 10.0 / (self.f * self.rx * self.rx * np.sqrt(4.*np.pi*self.rho))
        return self.interp_rx_dat(self.env.vAlf_raw) / np.sqrt(self.densfac)

    def __findVPh(self):
        # Phase Velocity in cm/s
        return self.vAlf + self.uw

    def __findVLOS(self, nGrad=None):
        if nGrad is not None:
            self.nGrad = nGrad
        else:
            self.nGrad = self.grid.ngrad
        self.vLOS = np.dot(self.nGrad, self.cU)
        # self.vLOS = self.alfU1 #FOR TESTING
        return self.vLOS

    def __findVLOS2(self, vel, nGrad=None):
        if nGrad is None: nGrad = self.grid.ngrad
        vLOS2 = np.dot(nGrad, vel)
        # print(self.vLOS2)
        return vLOS2

    def __findVPerp2(self, vel, nGrad=None):
        if nGrad is not None:
            self.nGrad = nGrad
        else:
            self.nGrad = self.grid.ngrad
        vPerp2 = np.cross(self.nGrad, vel)
        # print(self.vLOS2)
        return vPerp2

    def __findCU(self, pU):
        # Finds the cartesian velocity components
        [ur, uTheta, uPhi] = pU
        ux = -np.cos(self.pPos[2]) * (ur * np.sin(self.pPos[1]) + uTheta * np.cos(self.pPos[1])) - np.sin(
            self.pPos[2]) * uPhi
        uy = -np.sin(self.pPos[2]) * (ur * np.sin(self.pPos[1]) + uTheta * np.cos(self.pPos[1])) - np.cos(
            self.pPos[2]) * uPhi
        uz = ur * np.cos(self.pPos[1]) - uTheta * np.sin(self.pPos[1])
        return [ux, uy, uz]

    ## Time Dependence #######################################################################
    def findTwave(self):
        # Finds the wave travel time to this point
        # Approximate Version
        twave_min = 161.4 * (self.rx ** 1.423 - 1.0) ** 0.702741
        self.twave_fit = twave_min * self.densfac

        if self.findT and not self.wavesVsR:
            # Real Version
            radial = grid.sightline(self.foot_cPos, self.cPos)
            N = 10
            wtime = 0
            rLine = radial.cGrid(N)
            for cPos in rLine:
                point = simpoint(cPos, findT=False, grid=radial, env=self.env)
                wtime += (1 / point.vPh) / N
            self.twave = wtime * self.r2rx(radial.norm) * 69.63e9  # radius of sun in cm
            if self.twave < 0: self.twave = -256
        else:
            self.twave = self.twave_fit
        if not self.twave_fit == 0:
            self.twave_rat = self.twave / self.twave_fit
        else:
            self.twave_rat = np.nan

    def setTime(self, t=0):
        # Updates velocities to input time
        self.findWaveSpeeds(t)
        self.__findVLOS()

    ## Misc Methods ##########################################################################

    def find_nearest(self, array, value):
        # Returns the index of the point most similar to a given value
        array = array - value
        np.abs(array, out=array)
        return array.argmin()

    def interp_rx_dat(self, array):
        # Interpolates an array(rx)
        if self.rx < self.env.rx_raw[0]: return math.nan
        rxInd = np.int(np.searchsorted(self.env.rx_raw, self.rx) - 1)
        val1 = array[rxInd]
        val2 = array[rxInd + 1]
        slope = val2 - val1
        step = self.env.rx_raw[rxInd + 1] - self.env.rx_raw[rxInd]
        discreteRx = self.env.rx_raw[rxInd]
        diff = self.rx - discreteRx
        diffstep = diff / step
        return val1 + diffstep * (slope)

    def interp_rx_dat_log(self, array):
        return 10 ** (self.interp_rx_dat(np.log10(array)))

    def r2rx(self, r):
        return r / self.env.rstar

    def sph2cart(self, sph):
        # Change coordinate systems
        rho, theta, phi = sph[:]
        x = np.array(rho) * np.sin(np.array(theta)) * np.cos(np.array(phi))
        y = np.array(rho) * np.sin(np.array(theta)) * np.sin(np.array(phi))
        z = np.array(rho) * np.cos(np.array(theta))
        return [x, y, z]

    def cart2sph(self, cart):
        # Change coordinate systems
        x, y, z = cart[:]
        if x == 0: x = 1e-8
        if y == 0: y = 1e-8
        rho = np.sqrt(x ** 2 + y ** 2 + z ** 2)
        theta = np.arccos(z / rho)
        phi = np.arctan2(y, x)

        return [rho, theta, phi]

    def __absPath(self, path):
        # Converts a absative path to an absolute path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        abs = os.path.join(script_dir, path)
        return abs

    def show(self):
        # Print all properties and values
        myVars = vars(self)
        print("\nSimpoint Properties")
        for ii in sorted(myVars.keys()):
            print(ii, " : ", myVars[ii])

    def Vars(self):
        return vars(self)

    ## Level 1: Initializes many Simpoints into a Simulation


class simulate:
    plotSimProfs = False
    randTime = True
    makeLight = True
    # Level 1: Initializes many Simpoints into a Simulation
    def __init__(self, gridObj, envObj, N=None, iL=None, findT=None, printOut=False, timeAx=[0], getProf=False):
        comm = MPI.COMM_WORLD
        self.rank = comm.Get_rank()
        self.root = self.rank == 0
        self.size = comm.Get_size()

        self.inFindT = findT
        self.inIL = iL
        self.inN = N

        self.grid = gridObj
        self.grid.reset()
        self.print = printOut
        self.findT = findT
        self.env = envObj
        self.getProf = getProf
        self.timeAx = timeAx
        self.randomizeTime()

        self.ions = self.env.getIons(self.env.maxIons)

        self.throwCm = self.grid.norm * self.env.r_Mm * 1e8  # in cm
        self.sims = []
        self.point_grid(gridObj)

    def simulate_now(self):

        if type(self.grid) is grid.plane:
            doBar = True
            self.adapt = False
            self.Npoints = self.grid.Npoints
        else:
            doBar = False

        if doBar and self.print: bar = pb.ProgressBar(self.Npoints)

        self.sims = []
        self.steps = []
        self.pData = []

        self.grid.adapt = self.adapt

        stepInd = 0
        for cPos, step in self.grid:

            thisPoint = simpoint(cPos, self.grid, self.env, self.findT)

            # if self.adapt:
            #     # Adaptive Mesh
            #     rPos = thisPoint.pPos[0]
            #     planeDist = np.sqrt(cPos[0]**2 + cPos[1]**2)
            #     if rPos < 1.5 and self.grid.backflag1:
            #         self.grid.back()
            #         self.grid.set2minStep()
            #         self.grid.backflag1 = False
            #         continue
            #     elif planeDist < 5 and self.grid.backflag2:
            #         self.grid.back()
            #         self.grid.set2midStep()
            #         self.grid.backflag2 = False
            #         continue
            #     elif rPos > 5 and not self.grid.backflag2:
            #         self.grid.set2maxStep()
            #         self.grid.backflag2 = True
            #         self.grid.backflag1 = True

                # if (thisDens > tol) and self.grid.backflag:
                #     self.grid.back()
                #     self.grid.set2minStep()
                #     self.grid.backflag = False
                #     continue
                # if thisDens <= tol:
                #     self.grid.incStep(1.5)
                #     self.grid.backflag = True

            stepInd += 1

            self.sims.append(thisPoint)
            self.steps.append(step)
            self.pData.append(thisPoint.Vars())

            if doBar and self.print:
                bar.increment()
                bar.display()
        self.cumSteps = np.cumsum(self.steps)
        if doBar and self.print: bar.display(force=True)

        self.simFinish()

    def simFinish(self):
        self.Npoints = len(self.sims)
        if type(self.grid) is grid.sightline:
            self.shape = [self.Npoints, 1]
        else:
            self.shape = self.grid.shape
        self.shape2 = [self.shape[0], self.shape[1], -1]

    def point_grid(self, gridObj):
        self.grid = gridObj
        try:
            self.index = gridObj.index
        except:
            self.index = (0, 0, 0)

        if self.inFindT is None:
            self.findT = self.grid.findT
        else:
            self.findT = self.inFindT

        if self.inIL is None:
            self.iL = self.grid.iL
        else:
            self.iL = self.inIL

        if self.inN is None:
            self.N = self.grid.default_N
        else:
            self.N = self.inN

        if type(self.N) is list or type(self.N) is tuple:
            self.adapt = True
            self.grid.setMaxStep(1 / self.N[0])
            self.grid.setMinStep(1 / self.N[1])

        elif self.N == 'auto':
            self.adapt = True
            self.grid.setAutoN()
        else:
            self.adapt = False
            self.grid.setN(self.N)

        self.profile = None

        self.simulate_now()
        if self.getProf: self.lineProfile()

        return self

    def refreshData(self):
        self.pData = []
        for thisPoint in self.sims:
            self.pData.append(thisPoint.Vars())

    def get(self, myProperty, dim=None, scaling='None', scale=10, ion=None, refresh=False):
        if refresh: self.refreshData()
        if ion is None:
            propp = np.array([x[myProperty] for x in self.pData])
        else:
            # try:
            propp = np.array([x['ions'][ion][myProperty] for x in self.pData])
            # except:
            #     propp = np.array([x[myProperty] for x in self.pData])
        prop = propp.reshape(self.shape2)
        if not dim is None: prop = prop[:, :, dim]
        prop = prop.reshape(self.shape)
        if scaling.lower() == 'none':
            scaleProp = prop
        elif scaling.lower() == 'log':
            scaleProp = np.log10(prop) / np.log10(scale)
        elif scaling.lower() == 'root':
            scaleProp = prop ** (1 / scale)
        elif scaling.lower() == 'exp':
            scaleProp = prop ** scale
        elif scaling.lower() == 'norm':
            scaleProp = prop / np.amax(prop)
        else:
            print('Bad Scaling - None Used')
            scaleProp = prop
        return scaleProp

    def plot(self, property, dim=None, scaling='None', scale=10, ion=None, cmap='viridis', norm=False, threeD=False,
             useCoords=True,
             axes=False, center=False, linestyle='b', abscissa=None, absdim=0, yscale='linear', xscale='linear',
             extend='neither', sun=False, block=True,
             maximize=False, frame=False, ylim=None, xlim=None, show=True, refresh=False, useax=False, clabel=None,
             suptitle=None, savename=None, nanZero=True, **kwargs):
        unq = ""
        # Create the Figure and Axis
        if useax:
            ax = useax
            self.fig = ax.figure
        elif frame:
            self.fig, ax = self.grid.plot(iL=self.iL)
        elif threeD:
            self.fig = plt.figure()
            ax = self.fig.add_subplot(111, projection='3d')
        else:
            self.fig, ax = plt.subplots()

        if savename is not None: self.fig.canvas.set_window_title(str(savename))

        if suptitle is not None:
            self.fig.suptitle(suptitle)

        # Get the abscissa
        if abscissa is not None:
            absc = self.get(abscissa, absdim)
        else:
            absc = self.cumSteps

        # Condition the Inputs into lists
        if not isinstance(property, (list, tuple)):
            properties = [property]
        else:
            properties = property
        if not isinstance(dim, (list, tuple)):
            dims = [dim]
        else:
            dims = dim
        if not isinstance(scaling, (list, tuple)):
            scalings = [scaling]
        else:
            scalings = scaling
        if not isinstance(scale, (list, tuple)):
            scales = [scale]
        else:
            scales = scale

        # make sure they have the right lengths
        multiPlot = len(properties) > 1
        while len(dims) < len(properties): dims.append(None)
        while len(scalings) < len(properties): scalings.append('None')
        while len(scales) < len(properties): scales.append(1)

        # Condition the ion list
        if ion is None:
            useIons = [None]
        elif ion == -1:
            useIons = np.arange(len(self.ions))
        elif isinstance(ion, (tuple, list)):
            useIons = ion
        else:
            useIons = [ion]

        # Prepare the Plot Styles

        lines = ["-", "--", "-.", ":"]
        linecycler = cycle(lines)
        colors = ['C0', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9']
        colorcycler = cycle(colors)

        # Make the plotlist
        plotList = []
        plotLabels = []
        styles = []

        for ii in useIons:  # For each ion
            clr = next(colorcycler)
            linecycler = cycle(lines)
            for property, dim, scaling, scale in zip(properties, dims, scalings, scales):  # For each property
                ls = next(linecycler)

                # Get the data
                thisProp = np.ma.masked_invalid(self.get(property, dim, scaling, scale, ii, refresh))
                if nanZero: thisProp[thisProp == 0] = np.ma.masked
                if norm: thisProp = thisProp / np.max(thisProp)

                # Append to lists
                plotList.append(thisProp)
                labString = property
                if ii is not None: labString += ', {}_{}'.format(self.ions[ii]['eString'], self.ions[ii]['ionNum'])
                plotLabels.append(labString)
                styles.append(clr + ls)

        if type(self.grid) is grid.sightline:

            # Line Plot
            for prop, lab, style in zip(plotList, plotLabels, styles):
                im = ax.plot(absc, prop, style, label=lab, **kwargs)

            # Label Everything
            ax.legend()
            ax.set_xlabel(abscissa)
            if not multiPlot: ax.set_ylabel(property)
            ax.set_yscale(yscale)
            ax.set_xscale(xscale)
            if ylim is not None: ax.set_ylim(ylim)
            if xlim is not None: ax.set_xlim(xlim)
            if axes:
                ax.axhline(0, color='k')
                if abscissa is None:
                    ax.axvline(0.5, color='k')
                else:
                    ax.axvline(0, color='k')
                # ax.set_xlim([0,1])


        elif type(self.grid) is grid.plane:

            # Unpack the property
            scaleProp = plotList.pop()

            # Get the Coordinates of the points
            xx = self.get('cPos', 0)
            yy = self.get('cPos', 1)
            zz = self.get('cPos', 2)
            coords = [xx, yy, zz]

            # Find the throw in each dim
            xs = np.ptp(xx)
            ys = np.ptp(yy)
            zs = np.ptp(zz)
            diffs = [xs, ys, zs]

            # Find the small dimension and keep the others
            minarg = np.argmin(diffs)

            inds = [0, 1, 2]
            inds.remove(minarg)
            vind = inds.pop()
            hind = inds.pop()

            nind = 3 - vind - hind
            labels = ['X', 'Y', 'Z']

            hcoords = coords[hind]
            vcoords = coords[vind]
            ncoords = coords[nind]
            ax.set_xlabel(labels[hind])
            ax.set_ylabel(labels[vind])

            unq = np.unique(ncoords)
            if len(unq) > 1:
                otherax = "Non Constant"
            else:
                otherax = unq

            # Center the Color Scale
            if center:
                vmax = np.nanmax(np.abs(scaleProp))
                vmin = -vmax
            else:
                vmin, vmax = None, None

            if threeD:

                # Precondition
                xmin = np.min(np.min(scaleProp))
                xmax = np.max(np.max(scaleProp))
                newScale = (scaleProp - xmin) / (xmax - xmin)
                mapfunc = getattr(plt.cm, cmap)

                # Plot
                im = ax.plot_surface(xx, yy, zz, rstride=1, cstride=1, facecolors=mapfunc(newScale), shade=False)

                # Set plot limits
                xlm = ax.get_xlim()
                ylm = ax.get_ylim()
                zlm = ax.get_zlim()
                lims = [xlm, ylm, zlm]
                diffs = [np.abs(x[0] - x[1]) for x in lims]
                val, idx = max((val, idx) for (idx, val) in enumerate(diffs))
                goodlim = lims[idx]

                if nind == 1: ax.set_xlim(goodlim)
                if nind == 2: ax.set_ylim(goodlim)
                if nind == 3: ax.set_zlim(goodlim)

                ax.set_xlabel('X')
                ax.set_ylabel('Y')
                ax.set_zlabel('Z')

            else:

                hrez = np.abs(hcoords[1] - hcoords[0]) / 2
                vrez = np.abs(vcoords[1] - vcoords[0]) / 2
                if useCoords:
                    im = ax.pcolormesh(hcoords - hrez, vcoords - vrez, scaleProp, cmap=cmap, vmin=vmin, vmax=vmax,
                                       **kwargs)
                else:
                    im = ax.imshow(scaleProp, cmap=cmap, vmin=vmin, vmax=vmax, **kwargs)
                ax.set_aspect('equal')
                ax.patch.set(hatch='x', edgecolor='lightgrey')

                if axes:
                    ax.axhline(0, color='k')
                    ax.axvline(0, color='k')  # Plot axis lines

                try:
                    if frame:
                        self.fig.subplots_adjust(right=0.89)
                        cbar_ax = self.fig.add_axes([0.91, 0.10, 0.03, 0.8], autoscaley_on=True)
                        self.fig.colorbar(im, cax=cbar_ax, label=clabel, extend=extend)
                    else:
                        self.fig.colorbar(im, label=clabel, extend=extend)  # Put the colorbar
                except:
                    pass

            if sun:
                if threeD:
                    self.grid.plotSphere(ax, False)
                else:
                    sunCirc = plt.Circle((0, 0), 1, facecolor='orange', edgecolor='k')
                    ax.add_artist(sunCirc)

        else:
            print("Invalid Grid")
            return

        # Setting the Title
        if multiPlot: property = 'MultiPlot'

        zz = np.unique(self.get('cPos', 2))

        if len(zz) == 1: property = property + ", Z = {}".format(zz[0])

        if ion is None:
            ionstring = ''
        elif ion == -1:
            ionstring = 'All Ions'
        elif isinstance(ion, (list, tuple)):
            ionstring = 'MultiIon'
        elif isinstance(ion, int):
            i = self.ions[ion]
            ionstring = '{} : {} -> {}, $\lambda_0$: {} $\AA$'.format(i['ionString'], i['upper'], i['lower'], i['lam0'])
        else:
            assert False

        try:
            nmean = np.mean(ncoords)
            if np.unique(ncoords).size == 1:
                nval = nmean
            else:
                nval = "Varying"
        except:
            nval = "fail"

        if dim is None:
            try:
                ax.set_title(
                    property + ", scaling = " + scaling + ', {}={}, {}'.format(labels[nind], unq[0], ionstring))
            except:
                ax.set_title("{}, scaling = {}".format(property, scaling))
        else:
            ax.set_title(property + ", dim = " + dim.__str__() + ", scaling = " + scaling)

        # Finishing Moves
        if maximize and show: grid.maximizePlot()
        if show: plt.show(block)
        return ax

    def quiverPlot(self):
        dx, datSum = self.get('dx')
        dy, datSum = self.get('dy')
        delta, datSum = self.get('delta')
        plt.quiver(dx, dy, scale=50, color='w')
        rho, datsum = self.get('rho', scaling='log')
        plt.imshow(delta, interpolation="None")
        plt.show()

    def plot2(self, p1, p2, scaling1='None', scaling2='None', dim1=None, dim2=None, axes=True):
        scaleProp1, datSum1 = self.get(p1, dim1, scaling1)
        scaleProp2, datSum2 = self.get(p2, dim2, scaling2)
        datSum = datSum1
        self.fig, ax = self.grid.plot(iL=self.iL)
        if type(self.grid) is grid.sightline:
            # Line Plot
            im = ax.plot(self.cumSteps, scaleProp1, label=p1)
            im = ax.plot(self.cumSteps, scaleProp2, label=p2)
            if axes:
                ax.axhline(0, color='k')
                ax.axvline(0.5, color='k')
                ax.set_xlim([0, 1])
                ax.legend()
            datSum = datSum / self.N
        elif type(self.grid) is grid.plane:
            # Image Plot
            im = ax.imshow(scaleProp, interpolation='none', cmap=cmap)
            self.fig.subplots_adjust(right=0.89)
            cbar_ax = self.fig.add_axes([0.91, 0.10, 0.03, 0.8], autoscaley_on=True)
            self.fig.colorbar(im, cax=cbar_ax)
            datSum = datSum / self.N ** 2
        else:
            print("Invalid Grid")
            return

        if dim1 is None:
            ax.set_title(p1 + ", scaling = " + scaling1 + ', sum = {}'.format(datSum1) + '\n' +
                         p2 + ", scaling = " + scaling2 + ', sum = {}'.format(datSum2))
        else:
            ax.set_title(p1 + ", dim = " + dim1.__str__() + ", scaling = " + scaling + ', sum = {}'.format(datSum))

        grid.maximizePlot()
        plt.show()

    def compare(self, p1, p2, scaling1='None', scaling2='None', dim1=None, dim2=None, center=False):
        scaleprop = []
        scaleprop.append(self.get(p1, dim1, scaling1)[0])
        scaleprop.append(self.get(p2, dim2, scaling2)[0])
        fig, ax = self.grid.plot(iL=self.iL)
        fig.subplots_adjust(right=0.89)
        cbar_ax = fig.add_axes([0.91, 0.10, 0.03, 0.8], autoscaley_on=True)
        if center:
            vmax = np.nanmax(np.abs(scaleprop[0]))
            vmin = - vmax
        else:
            vmax = vmin = None

        global cur_plot
        cur_plot = 0

        def plot1():
            im = ax.imshow(scaleprop[0], interpolation='none', vmin=vmin, vmax=vmax)
            ax.set_title(p1)
            fig.colorbar(im, cax=cbar_ax)
            fig.canvas.draw()

        def plot2():
            im = ax.imshow(scaleprop[1], interpolation='none', vmin=vmin, vmax=vmax)
            ax.set_title(p2)
            fig.colorbar(im, cax=cbar_ax)
            fig.canvas.draw()

        plots = [plot1, plot2]

        def onKeyDown(event):
            global cur_plot
            cur_plot = 1 - cur_plot
            plots[cur_plot]()

        cid = fig.canvas.mpl_connect('key_press_event', onKeyDown)

        grid.maximizePlot()
        plt.show()

    def show(self, short=False):
        # Print all properties and values
        myVars = vars(self.sims[0])
        print("\nSimpoint Properties")
        for ii in sorted(myVars.keys()):
            var = myVars[ii]

            if not short: print(ii, " : ", var)
            if short:
                p = False
                try:
                    l = len(var)
                    if l < 10: p = True
                except:
                    p = True
                if p: print(ii, " : ", var)

    def Vars(self):
        # Returns the vars of the simpoints
        return self.sims[0].Vars()

    def Keys(self):
        # Returns the keys of the simpoints
        return self.sims[0].Vars().keys()

    ####################################################################

    # def getProfile(self):
    #    return self.lineProfile()

    def plotProfile(self, which='R', norm=False):

        prof = 'profile' + which

        try:
            self.ions[0][prof]
        except:
            self.lineProfile()

        for ion in self.ions:
            if norm:
                pl = ion[prof] / np.max(ion[prof])
            else:
                pl = ion[prof]
            plt.plot(pl)

        plt.title("Line Profile")
        plt.ylabel("Intensity")
        plt.xlabel("Wavelenght (A)")
        # plt.yscale('log')
        plt.show()

    def randomizeTime(self):
        self.env.timeRand.seed(int(self.env.primeSeed + self.rank))
        self.rOffset = self.env.timeRand.randint(self.env.tmax)
        if self.randTime:
            self.timeAx = [t + self.rOffset for t in self.timeAx]

    def lineProfile(self, times=None, ions=None):
        weightPower = self.env.weightPower
        if not times: times = self.timeAx
        if ions is None: ions = self.ions
        if not type(ions) is list: ions = [ions]
        if not type(times) is list: times = [times]
        # if not hasattr(self, 'profilesC'):

        # Get a line profile integrated over time
        profilesC = []
        profilesR = []
        for ion in ions:
            # Create an empty box for the profiles to be put in
            profilesC.append(np.zeros_like(ion['lamAx']))
            profilesR.append(np.zeros_like(ion['lamAx']))

        # Initialize plot stuff
        plotIon = ions[-1]
        plotLam = plotIon['lamAx'] - plotIon['lam00']
        if self.plotSimProfs: fig, axarray = plt.subplots(nrows=2, ncols=1, sharex=True, figsize=(4.1, 6), dpi=200)

        # Initialize values
        ppC = []
        ppR = []
        scale = 4
        urProj = 0
        rmsProj = 0
        temProj = 0
        rho2 = 0
        pB = 0

        if self.print and self.root:
            print('\nGenerating Light...')
            bar = pb.ProgressBar(len(self.sims) * len(times))

        # Primary Loop
        for point, step in zip(self.sims, self.steps):
            # For each simpoint
            lenCm = step * self.throwCm

            for tt in times:
                # For each time
                point.setTime(tt)
                if self.makeLight:
                    newProfiles = point.getProfiles(lenCm, ions)

                    for profileC, profileR, (newProfC, newProfR) in zip(profilesC, profilesR, newProfiles):
                        # For each Ion, Sum the light
                        profileC += newProfC
                        profileR += newProfR

                if self.plotSimProfs:
                    # Some plot things
                    bigprofC = profC * 10 ** scale
                    bigprofR = profR * 10 ** scale
                    ppC.append(bigprofC)
                    ppR.append(bigprofR)

                # Sum the ion independent things
                # pB += point.dPB * step
                urProj += point.urProj * step
                rmsProj += point.rmsProj * step
                temProj += point.temProj * step
                rho2 += point.rho ** weightPower * step

                if self.print and self.root:
                    bar.increment()
                    bar.display()

                if self.plotSimProfs: axarray[1].plot(plotLam, bigprofC)

        if self.plotSimProfs:
            axarray[1].plot(plotLam, profileC * 10 ** scale, 'k')
            axarray[0].plot(plotLam, profileC * 10 ** scale, 'k')
            axarray[0].stackplot(plotLam, np.asarray(ppC))

            axarray[1].set_yscale('log')
            axarray[1].set_ylim([1e-9 * 10 ** scale, 5e-4 * 10 ** scale])
            axarray[0].set_ylim([0, 2.5])
            axarray[1].set_xlim([1030 - plotion['lam00'], 1033.9 - plotion['lam00']])
            fig.text(0.005, 0.5, 'Intensity (Arb. Units)', va='center', rotation='vertical')
            # axarray[0].set_ylabel('Intensity (Arb. Units)')
            # axarray[1].set_ylabel('Intensity (Arb. Units)')
            axarray[1].set_xlabel('Wavelength ($\AA$)')

            # grid.maximizePlot()
            # plt.suptitle('Contributions to a single profile')
            plt.show()

        for ion, profileC, profileR in zip(ions, profilesC, profilesR):
            # Store the summed profiles for each ion
            ion['profileC'] = profileC
            ion['profileR'] = profileR

        self.profilesC = profilesC
        self.profilesR = profilesR
        # self.pB = pB
        self.urProj = np.sqrt(urProj / rho2)
        self.rmsProj = np.sqrt(rmsProj / rho2)
        self.temProj = (temProj / rho2)

        for point in self.sims:  # Not sure how to normalize this
            point.urProjRel = np.sqrt(point.urProj / urProj / rho2)
            point.rmsProjRel = np.sqrt(point.rmsProj / rmsProj / rho2)

        # plt.plot(profile)
        # plt.show()
        if self.print and self.root: bar.display(True)
        return self.profilesC, self.profilesR

    def removeEnv(self):
        del self.env
        for sim in self.sims:
            del sim.env

    ## Time Dependence ######################################################
    def setTime(self, tt=0):
        for point in self.sims:
            point.setTime(tt)

    def makeSAxis(self):
        loc = 0
        ind = 0
        self.sAxis = np.zeros_like(self.steps)
        for step in self.steps:
            loc += step
            self.sAxis[ind] = loc
            ind += 1
        self.sAxisList = self.sAxis.tolist()

    def peekLamTime(self, lam0=1000, lam=1000, t=0):
        self.makeSAxis()
        intensity = np.zeros_like(self.sims)
        pInd = 0
        for point in self.sims:
            point.setTime(t)
            intensity[pInd] = point.findIntensity(lam0, lam)
            pInd += 1
        plt.plot(self.sAxis, intensity, '-o')
        plt.show()

    def evolveLine(self, times, ion=0):
        # Get the line profile over time and store in LineArray
        print('Timestepping...')
        if type(ion) is int: ion = self.ions[ion]

        lamAx = ion['lamAx']
        tN = len(times)
        lN = len(lamAx)
        lineArray = np.zeros((tN, lN))

        useRez = 1 if batchjob.resonant else 0
        useCol = 1 if batchjob.collisional else 0

        bar = pb.ProgressBar(len(times))
        for ind, tt in enumerate(times):
            profC, profR = self.lineProfile(tt, ion)
            thisProf = np.asarray(profC) * useCol + np.asarray(profR) * useRez
            lineArray[ind][:] = thisProf
            bar.increment()
            bar.display()
        bar.display(force=True)

        self.lineList = lineArray.tolist()

        plt.pcolormesh(lamAx, times, lineArray)
        plt.xlabel('Wavelength in Angstroms')
        plt.ylabel('Time (s)')
        plt.title("Spectra have a lot of Structure")
        plt.show()

    def plotProfileT(self, t, ion):
        if type(ion) is int: ion = self.ions[ion]

        useRez = 1 if batchjob.resonant else 0
        useCol = 1 if batchjob.collisional else 0

        profC, profR = self.lineProfile(t, ion)
        thisProf = np.asarray(profC[0]) * useCol + np.asarray(profR[0]) * useRez

        results = self.fit_gaussian(thisProf, ion)

        plt.plot(ion['lamAx'], thisProf, label='Profile')
        plt.plot(ion['lamAx'], self.gauss_function(ion['lamAx'], *results), label='Curve Fit')

        plt.xlim((194.9, 195.3))
        plt.xlabel("Wavelength")
        plt.ylabel("Intensity")
        plt.title("Example Curve Fit")
        plt.legend()
        plt.show()




    def gauss_function(self, x, a, x0, sigma):
        return a * np.exp(-(x - x0) ** 2 / (2 * sigma ** 2))

    def fit_gaussian(self, profile, ion):

        sig0 = sum((ion['lamAx'] - ion['lam00']) ** 2) / len(profile)
        amp0 = np.max(profile)

        popt, pcov = curve_fit(self.gauss_function, ion['lamAx'], profile, p0=[amp0, ion['lam00'], sig0])
        amp = popt[0]
        mu = popt[1] #- ion['lam00']
        std = popt[2]
        return amp, mu, std


    def evolveLine_old(self, tn=150, t0=0, t1=4000):
        # Get the line profile over time and store in LineArray
        print('Timestepping...')

        # self.lam0 = lam0
        self.times = np.linspace(t0, t1, tn)
        # self.makeLamAxis(self, Ln, lam0, lamPm)
        self.lineArray = np.zeros((tn, self.env.Ln))

        bar = pb.ProgressBar(len(self.times))
        timeInd = 0
        for tt in self.times:
            self.timeAx = [tt]
            self.lineArray[timeInd][:] = self.lineProfile()[0]
            bar.increment()
            bar.display()
            timeInd += 1
        bar.display(force=True)

        self.lineList = self.lineArray.tolist()





        # self.timeStats()
        # self.slidingWindow()
        # self.windowPlot()
        # self.__fitGaussians_t()
        # self.__findMoments_t()
        # self.plotLineArray_t()

    def timeStats(self):
        self.mybatch = batch('noRand').loadBatch()
        self.mybatch.makePSF()
        self.mybatch.II = 0
        self.mybatch.impact = self.sims[0].cPos[2]

        # bar = pb.ProgressBar(len(self.times))
        # for profile in self.lineList:
        #    p = self.mybatch.findProfileStats(profile)
        #    self.centroid.append(p[1])
        #    self.sigma.append(p[2])
        #    bar.increment()
        #    bar.display()
        # bar.display(force = True)

    def slidingWindow(self, lineArray, times):

        profileNorm = True
        logbreak = 10

        # Get the Arrays
        profiles = lineArray

        # Calculate bounds
        nT, nL = lineArray.shape

        longestWindow = nT // 1.5

        self.firstIndex = 0  # longestWindow + 1
        self.lastIndex = nT - 1

        theBreak = min(longestWindow / logbreak, 100)

        linpart = np.arange(theBreak)
        logpart = np.logspace(np.log10(theBreak), np.log10(longestWindow), 100)
        self.winAx = np.concatenate((linpart, logpart)).astype(int)
        self.nWin = len(self.winAx)
        self.nLam = len(profiles[0][:])

        # Generate SlideList/SlideArray
        slideProfiles = []
        slideCentroids = []
        slideSigmas = []

        print("Windowing...")
        bar = pb.ProgressBar(nT)
        bar.display()

        for tt in times:
            # For every timestep

            # Get the window
            shiftedProfiles = np.flipud(self.getMaxWindow(profiles, tt, longestWindow, nT))

            # Initialize variables
            profile = np.zeros(self.nLam)
            winArray = np.zeros((self.nWin, self.nLam))
            TT = 0
            ww = 0
            centList = []
            sigList = []

            for window in self.winAx:
                # Sum profiles until current window length
                while window >= TT:
                    profile += shiftedProfiles[TT]
                    TT += 1

                # profile = self.getWindow(profiles,tt,window,NT)

                if profileNorm:
                    outProf = profile / np.sum(profile)
                else:
                    outProf = profile

                winArray[ww] = outProf
                ww += 1

                # p = self.mybatch.findProfileStats(profile)
                p = batchjob.findMomentStats(profile)
                centList.append(p[1])
                sigList.append(p[2])

            # Append that whole list as one timepoint
            # slideProfiles.append(np.asarray(winList))
            slideProfiles.append(winArray)
            slideCentroids.append(np.asarray(centList))
            slideSigmas.append(np.asarray(sigList))
            # plt.pcolormesh(winArray)
            # plt.show()

            bar.increment()
            bar.display()
        bar.display(force=True)

        # Convert to arrays
        self.slideArray = np.asarray(slideProfiles)
        self.slideCents = np.asarray(slideCentroids)
        self.slideSigs = np.asarray(slideSigmas)

        # Get statistics on centroids
        self.centDt = 100
        varCentsL = []
        for tt in self.times:
            range = self.makeRange(tt, self.centDt, NT)

            centroids = self.slideCents[range]
            varience = np.std(centroids, axis=0)
            varCentsL.append(varience)
        self.varCents = np.asarray(varCentsL)

        self.cents = np.std(self.slideCents, axis=0)

    def getWindow(self, profiles, tt, window, NT):
        """Get the binned profile at given time with given window"""
        range = self.makeRange(tt, window, NT)
        profilez = np.sum(profiles[range][:], axis=0)
        return profilez

    def getMaxWindow(self, profiles, tt, window, NT):
        range = self.makeRange(tt, window, NT)
        return profiles[range][:]

    def makeRange(self, tt, window, NT):
        range = np.arange(-window, 1) + tt
        range = np.mod(range, NT).astype(int)
        return range

        # start = tt-window
        # end = tt + 1

        ##low = math.fmod(tt-window, NT)
        # low = np.mod(tt-window, -NT)
        # high = np.mod(tt+1, NT)
        ##if low > high: low, high = high, low
        # range = np.arange(low,high)

    def windowPlot(self):

        # Create all the axes
        from matplotlib import gridspec
        gs = gridspec.GridSpec(1, 3, width_ratios=[3, 3, 1])
        fig = plt.figure()
        mAx = plt.subplot(gs[0])
        slAx = plt.subplot(gs[1], sharex=mAx)
        vAx = plt.subplot(gs[2], sharey=slAx)

        # fig, [mAx, slAx, vAx] = plt.subplots(1,3, sharey = True, gridspec_kw = {'width_ratios':[1, 4, 1]})
        tit = fig.suptitle("Time: {}".format(self.firstIndex))

        # Just the regular time series with ticker line
        vmax = np.amax(self.lineArray) * 0.7
        vmin = np.amin(self.lineArray) * 0.9
        mAx.pcolormesh(self.env.lamAx.astype('float32'), self.times, self.lineArray, vmin=vmin, vmax=vmax)
        slide = 0.2
        mAx.set_xlim(self.env.lam0 - slide, self.env.lam0 + slide)
        mAx.set_ylabel('Time')
        mAx.set_title('Time Series')
        tickerLine = mAx.axhline(0)

        # The sliding window plot
        slAx.set_title('Integration View')
        slAx.set_xlabel("Wavelength")
        slAx.set_ylabel("Integration Time (S)")
        slAx.set_ylim(0, np.amax(self.winAx))
        quad = slAx.pcolormesh(self.env.lamAx, self.winAx, self.slideArray[self.lastIndex])

        # The centroid line
        line1, = slAx.plot(self.slideCents[self.lastIndex], self.winAx, 'r')
        slAx.axvline(self.env.lam0, color='k', ls=":")

        # THe sigma lines
        line2, = slAx.plot(self.slideCents[self.lastIndex] + self.slideSigs[self.lastIndex], self.winAx, 'm')
        line3, = slAx.plot(self.slideCents[self.lastIndex] - self.slideSigs[self.lastIndex], self.winAx, 'm')

        # Centroid Sigma
        vCents = self.mybatch.std2V(self.cents)
        self.vSigs = self.mybatch.std2V(self.slideSigs)
        vAx.plot(vCents, self.winAx)
        vAx.axvline(color='k')
        vAx.set_title("St. Dev. of the Centroid")
        # line4, = vAx.plot(self.vSigs[self.lastIndex], self.winAx)
        # throw = np.nanmax(self.varCents)
        # vAx.set_xlim(0,throw)
        # vAx.set_title('Varience of the Centroid \nfor {}s'.format(self.centDt))
        vAx.set_xlabel('km/s')

        def init():
            tit.set_text("Time: {}".format(self.lastIndex))
            tickerLine.set_ydata(self.lastIndex)
            quad.set_array(self.slideArray[self.lastIndex][:-1, :-1].flatten())
            line1.set_xdata(self.slideCents[self.lastIndex])
            line2.set_xdata(self.slideCents[self.lastIndex] + self.slideSigs[self.lastIndex])
            line3.set_xdata(self.slideCents[self.lastIndex] - self.slideSigs[self.lastIndex])
            # line4.set_xdata(self.vSigs[self.lastIndex])
            return tickerLine, quad, line1, line2, line3, tit

        # Animate
        from matplotlib import animation

        def animate(i):
            tit.set_text("Time: {}".format(i))
            tickerLine.set_ydata(i)
            quad.set_array(self.slideArray[i][:-1, :-1].flatten())
            line1.set_xdata(self.slideCents[i])
            line2.set_xdata(self.slideCents[i] + self.slideSigs[i])
            line3.set_xdata(self.slideCents[i] - self.slideSigs[i])
            # line4.set_xdata(self.vSigs[i])
            return tickerLine, quad, line1, line2, line3

        anim = animation.FuncAnimation(fig, animate, init_func=init, frames=np.arange(self.firstIndex, self.lastIndex),
                                       repeat=True, interval=75, blit=True)

        grid.maximizePlot()
        plt.show(False)
        plt.close()
        anim.save(filename=self.movName, writer='ffmpeg', bitrate=1000)
        print('Save Complete')
        # plt.tight_layout()
        # plt.show()

        return

    def __findMoments_t(self):
        # Find the moments of each line in lineList
        self.maxMoment = 3
        self.moment = []
        lineInd = 0
        for mm in np.arange(self.maxMoment):
            self.moment.append(np.zeros_like(self.times))

        for line in self.lineList:
            for mm in np.arange(self.maxMoment):
                self.moment[mm][lineInd] = np.dot(line, self.env.lamAx ** mm)
            lineInd += 1

        self.__findMomentStats_t()
        # self.plotMoments_t()
        return

    def __findMomentStats_t(self):
        self.power = self.moment[0]
        self.centroid = self.moment[1] / self.moment[0]
        self.sigma = np.sqrt(self.moment[2] / self.moment[0] - (self.moment[1] / self.moment[0]) ** 2)
        # self.plotMomentStats_t()

    def plotMomentStats_t(self):
        f, (ax1, ax2, ax3) = plt.subplots(3, 1, sharex=True)
        f.suptitle('Moments Method')
        ax1.plot(self.times, self.power)
        ax1.set_title('0th Moment')
        ax1.get_yaxis().get_major_formatter().set_useOffset(False)
        ax1.get_yaxis().get_major_formatter().set_scientific(True)

        ax2.plot(self.times, self.centroid)
        ax2.set_title('Centroid')
        ax2.set_ylabel('Angstroms')

        ax3.plot(self.times, self.sigma)
        ax3.set_ylabel('Angstroms')
        ax3.set_title('Std')
        ax3.set_xlabel('Time (s)')
        plt.show(False)

    def plotMoments_t(self):
        f, axArray = plt.subplots(self.maxMoment, 1, sharex=True)
        mm = 0
        for ax in axArray:
            ax.plot(self.times, self.moment[mm])
            ax.set_title(str(mm) + " Moment")
            ax.set_ylabel('Angstroms')
            mm += 1
        ax.set_xlabel('Time (s)')
        plt.show(False)

    def plotLineArray_t(self):
        ## Plot the lineArray
        self.fig, ax = self.grid.plot(iL=self.iL)

        im = ax.pcolormesh(self.env.lamAx.astype('float32'), self.times, self.lineArray)
        # ax.xaxis.get_major_formatter().set_powerlimits((0, 1))
        ax.set_xlabel('Angstroms')
        ax.set_ylabel('Time (s)')
        self.fig.subplots_adjust(right=0.89)
        cbar_ax = self.fig.add_axes([0.91, 0.10, 0.03, 0.8], autoscaley_on=True)
        self.fig.colorbar(im, cax=cbar_ax)

        # Plot the Centroid vs Time
        self.fig.subplots_adjust(right=0.7)
        cent_ax = self.fig.add_axes([0.74, 0.10, 0.15, 0.8], autoscaley_on=True)
        cent_ax.set_xlabel('Centroid')

        cent_ax.plot(self.centroid, self.times)
        cent_ax.axvline(self.env.lam0)

        # cent_ax.set_xlim([np.min(self.env.lamAx), np.max(self.env.lamAx)])
        cent_ax.xaxis.get_major_formatter().set_useOffset(False)
        max_xticks = 4
        xloc = plt.MaxNLocator(max_xticks)
        cent_ax.xaxis.set_major_locator(xloc)

        grid.maximizePlot()
        plt.show(False)

    def __fitGaussians_t(self):
        self.amp = np.zeros_like(self.times)
        self.mu = np.zeros_like(self.times)
        self.std = np.zeros_like(self.times)
        self.area = np.zeros_like(self.times)

        def gauss_function(x, a, x0, sigma):
            return a * np.exp(-(x - x0) ** 2 / (2 * sigma ** 2))

        lInd = 0
        for line in self.lineList:
            sig0 = sum((self.env.lamAx - self.env.lam0) ** 2) / len(line)
            amp0 = np.max(line)
            popt, pcov = curve_fit(gauss_function, self.env.lamAx, line, p0=[amp0, self.env.lam0, sig0])
            self.amp[lInd] = popt[0]
            self.mu[lInd] = popt[1] - self.env.lam0
            self.std[lInd] = popt[2]
            self.area[lInd] = popt[0] * popt[2]

            ## Plot each line fit
            # plt.plot(self.lamAx, gauss_function(self.lamAx, amp[lInd], mu[lInd], std[lInd]))
            # plt.plot(self.lamAx,  lineList[lInd])
            # plt.show()
            lInd += 1

        # self.plotGaussStats_t()

    def plotGaussStats_t(self):
        f, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1, sharex=True)
        f.suptitle('Gaussian method')
        ax1.plot(self.times, self.amp)
        ax1.set_title('Amplitude')
        ax2.plot(self.times, self.mu)
        ax2.set_title('Mean')
        ax2.set_ylabel('Angstroms')
        ax3.plot(self.times, self.std)
        ax3.set_ylabel('Angstroms')
        ax3.set_title('Std')
        ax4.plot(self.times, self.area)
        ax4.set_title('Area')
        ax4.set_xlabel('Time (s)')
        plt.show(False)


## Level 2: Initializes many simulations (MPI Enabled) for statistics
class multisim:
    keepAll = False
    useMasters = False
    # Level 2: Initializes many simulations
    def __init__(self, batch, env, N=1000, findT=None, printOut=False, printSim=False, timeAx=[0], printQuiet=False):
        self.print = printOut
        self.printSim = printSim
        self.printQuiet = printQuiet
        self.timeAx = timeAx
        # self.gridLabels = batch[1]
        self.oneBatch = batch

        self.N = N
        self.findT = findT

        comm = MPI.COMM_WORLD
        self.rank = comm.Get_rank()
        self.root = self.rank == 0
        self.size = comm.Get_size()

        self.env = env

        self.batch = self.oneBatch
        assert len(self.batch) > 0

        # self.batch = []
        # self.envInd = []
        # if type(envs) is list or type(envs) is tuple:

        #    self.envs = envs
        #    self.Nenv = len(self.envs)
        #    import copy
        #    for nn in np.arange(self.Nenv):
        #        self.batch.extend(copy.deepcopy(self.oneBatch))
        #        self.envInd.extend([nn] * len(self.oneBatch))
        # else:
        #    self.envs = [envs]
        #    self.batch = self.oneBatch
        #    self.envInd = [0] * len(self.oneBatch)

        self.initLists()

        if comm.size > 1 and not self.printQuiet:
            self.run_multisim_MPI_MS()
        else:
            self.run_multisim_serial()

        # self.findProfiles()

    def init_Masterlines(self):
        self.masterLine = []
        ind = 0
        grd = grid.defGrid().primeLineLong
        for env in self.envs:
            grd.reset()
            # simulation = simulate(grd, self.envs[ind], self.N, findT = self.findT, timeAx = self.timeAx, printOut = self.printSim, getProf = True)
            self.masterLine.append(
                simulate(grd, self.envs[ind], self.N, findT=False, timeAx=self.timeAx, printOut=self.printSim,
                         getProf=True))
            ind += 1

    def run_multisim_MPI_MS(self):

        if self.root and self.print:
            print('Running MultiSim: ' + time.asctime())
            t = time.time()  # Print Stuff
            try:
                print('Nenv = ' + str(self.env.Nenv), end='; ')
                print('Lines\Env = ' + str(self.env.Nrot), end='; ')
            except: pass

            print('JobSize = ' + str(len(self.batch)), end='; ')

            print('PoolSize = ' + str(self.size - 1), end='; ')
            # print('ChunkSize = ' + str(len(self.gridList)), end = '; ')
            # print('Short Cores: ' + str(self.size * len(self.gridList) - len(self.batch)))#Print Stuff
            print('')
            self.Bar = pb.ProgressBar(len(self.batch), label='Lines')
            self.Bar.display()
        else:
            self.Bar = None

        if self.useMasters: self.init_Masterlines()

        # work = [[bat,env] for bat,env in zip(self.batch, self.envInd)]
        work = self.batch

        self.poolMPI(work, self.simulate_line)

        try:
            self.Bar.display(force=True)
            sys.stdout.flush()
        except:
            pass
        #
        # if self.destroySims and self.root: self.sims = self.sims[0:1]

    def initLists(self):
        self.sims = []
        self.profilesC = []
        self.intensitiesC = []
        self.profilesR = []
        self.intensitiesR = []
        self.pBs = []
        self.urProjs = []
        self.rmsProjs = []
        self.temProjs = []
        self.indices = []

    def collectVars(self, simulation):
        if self.keepAll:
            self.sims.append(simulation)
        else:
            self.sims = [simulation]
        self.profilesC.append(simulation.profilesC)
        self.intensitiesC.append(np.sum(simulation.profilesC))
        self.profilesR.append(simulation.profilesR)
        self.intensitiesR.append(np.sum(simulation.profilesR))
        # self.pBs.append(simulation.pB)
        self.urProjs.append(simulation.urProj)
        self.rmsProjs.append(simulation.rmsProj)
        self.temProjs.append(simulation.temProj)
        self.indices.append(simulation.index)

    def simulate_line(self, grd):

        simulation = simulate(grd, self.env, self.N, findT=self.findT, timeAx=self.timeAx, printOut=self.printSim,
                              getProf=True)

        return simulation

    # def workrepoint(self, grd, envInd):
    #     return self.masterLine[envInd].point_grid(grd)

    def __seperate(self, list, N):
        # Breaks a list up into chunks
        import copy
        newList = copy.deepcopy(list)
        Nlist = len(newList)
        chunkSize = float(Nlist / N)
        chunks = [[] for _ in range(N)]
        chunkSizeInt = int(np.floor(chunkSize))

        if chunkSize < 1:
            remainder = Nlist
            chunkSizeInt = 0
            if self.root: print(' **Note: All PEs not being utilized** ')
        else:
            remainder = Nlist - N * chunkSizeInt

        for NN in np.arange(N):
            thisLen = chunkSizeInt
            if remainder > 0:
                thisLen += 1
                remainder -= 1
            for nn in np.arange(thisLen):
                chunks[NN].extend([newList.pop(0)])
        return chunks

    def run_multisim_serial(self):
        # Serial Version
        work = self.batch
        self.sims = []
        if self.print:
            self.Bar = pb.ProgressBar(len(work))
            self.Bar.display()

        for line in work:
            self.collectVars(self.simulate_line(line))
            if self.print:
                self.Bar.increment()
                self.Bar.display()

        nFinish = len(self.indices)
        if self.print:
            print('\nConfirmed: {} Lines Simulated'.format(nFinish))

    def plotLines(self):
        axes = self.oneBatch[0].quadAxOnly()
        for line in self.oneBatch:
            line.plot(axes=axes)
        plt.show()

    def dict(self):
        """
        Determine existing fields
        """
        return {field: getattr(self, field)
                for field in dir(self)
                if field.upper() == field
                and not field.startswith('_')}

    def getSmall(self):
        profilesC = self.profilesC
        profilesR = self.profilesR

        for field in self.dict():
            delattr(self, field)

        self.profilesC = profilesC
        self.profilesR = profilesR
        print(vars(self))
        return self

    def master(self, wi):
        WORKTAG = 0
        DIETAG = 1
        all_data = []
        size = MPI.COMM_WORLD.Get_size()
        current_work = self.__Work__(wi)
        comm = MPI.COMM_WORLD
        status = MPI.Status()
        for i in range(1, size):
            anext = current_work.get_next_item()
            if not anext: break
            comm.send(anext, dest=i, tag=WORKTAG)

        while 1:
            anext = current_work.get_next_item()
            if not anext: break
            data = comm.recv(None, source=MPI.ANY_SOURCE, tag=MPI.ANY_TAG, status=status)
            self.collectVars(data)
            all_data.append([])
            try:
                self.Bar.increment()
                self.Bar.display()
            except:
                pass
            comm.send(anext, dest=status.Get_source(), tag=WORKTAG)

        for i in range(1, size):
            data = comm.recv(None, source=MPI.ANY_SOURCE, tag=MPI.ANY_TAG)
            self.collectVars(data)
            all_data.append([])
            try:
                self.Bar.increment()
                self.Bar.display()
            except:
                pass

        for i in range(1, size):
            comm.send(None, dest=i, tag=DIETAG)

        return all_data

    def slave(self, do_work):
        comm = MPI.COMM_WORLD
        status = MPI.Status()
        while 1:
            data = comm.recv(None, source=0, tag=MPI.ANY_TAG, status=status)
            if status.Get_tag(): break
            result = do_work(data)
            result.removeEnv()
            comm.send(result, dest=0)

    def poolMPI(self, work_list, do_work):
        rank = MPI.COMM_WORLD.Get_rank()
        name = MPI.Get_processor_name()
        size = MPI.COMM_WORLD.Get_size()

        if rank == 0:
            all_dat = self.master(work_list)
            return all_dat
        else:
            self.slave(do_work)
            return None

    class __Work__():
        def __init__(self, work_items):
            self.work_items = work_items[:]

        def get_next_item(self):
            if len(self.work_items) == 0:
                return None
            return self.work_items.pop()

        ## Level 3: Initializes many Multisims, varying a parameter. Does statistics. Saves and loads Batches.


class batch:
    def __init__(self, batchname, env=None):
        self.batchName = batchname
        self.env = env
        comm = MPI.COMM_WORLD
        self.rank = comm.Get_rank()
        self.root = self.rank == 0

    # Handles loading and running of batches
    def restartBatch(self, env=None):
        """Finish simulating an incomplete job"""
        env = self.getEnv(env)
        myBatch = self.loadBatch(env)
        myBatch.simulate_batch()
        return myBatch

    def analyzeBatch(self, env=None, storeF=False):
        """Run statistical analysis of a completed job"""
        myBatch = self.loadBatch(env)
        myBatch.doStats()
        myBatch.plot()
        if storeF: myBatch.storeFfiles(storeF)
        return myBatch

    def loadBatch(self, env=None):
        """Return a batchjob from file and make it useable"""
        env = self.getEnv(env)
        env.assignColors()
        myBatch = self.__loadBatchFile()
        myBatch.reloadEnv(env)
        myBatch.reassignColors()
        myBatch.findRank()
        return myBatch

    def renameBatch(self, newName, env=None):
        env = self.getEnv(env)
        myBatch = self.loadBatch(env)
        myBatch.rename(newName)
        return myBatch

    def getEnv(self, env=None):
        if not env: env = self.env
        return env

    def __loadBatchFile(self, printout=False):
        """Load a batchjob from file"""
        if self.root and printout: print("Loading Batch: {}".format(self.batchName))
        batchPath = '../dat/batches/{}.batch'.format(self.batchName)
        absPth = os.path.normpath(batchPath)
        try:
            with open(absPth, 'rb') as input:
                return pickle.load(input)
        except:
            sys.exit('Batch Not found')


class batchjob:
    qcuts = [16, 50, 84]
    doLinePlot = False

    resonant = True
    collisional = True

    usePsf = False
    reconType = 'sub'  # 'Deconvolution' or 'Subtraction' or 'None'
    plotbinFits = False  # Plots the binned and the non-binned lines, and their fits, during stats only
    plotheight = 1
    histMax = 50

    saveSims = False

    plotFits = False  # Plots the Different fits to the line w/ the raw line
    maxFitPlot = 10

    hahnPlot = False  # Plot the green Hahn Data on the primary plot
    plotRatio = False  # Plot the ratio of the reconstruction/raw fits

    ## Run the Simulation ######################################################
    def __init__(self):

        self.ions = self.env.getIons(self.env.maxIons)
        self.reassignColors()
        self.firstRunEver = True
        self.statsDone = False
        self.complete = False
        self.completeTime = "Incomplete Job"
        comm = MPI.COMM_WORLD
        self.root = comm.rank == 0
        self.intTime = len(self.timeAx)
        self.simulate_batch()
        self.finish()
        

    def simulate_batch(self):

        comm = MPI.COMM_WORLD

        if self.root and self.print:
            print('\nCoronaSim!')
            print('Written by Chris Gilbert')
            print('-------------------------\n')
            print("Simulating Impacts: {}".format(self.impacts))
            print("Ions: {}".format([x['ionString'] for x in self.ions]))
            print("Integration Time: {} seconds".format(len(self.timeAx)))
            sys.stdout.flush()

        if self.firstRunEver:
            self.count = 0
            self.batch = self.fullBatch
            self.initLists()
            if (self.root and self.print) or self.printQuiet:
                self.bar = pb.ProgressBar(len(self.impacts), label=self.batchName)

            self.doLabels = self.impacts.tolist()
            self.rAxisMain = []
            self.zAxisMain = []
        elif self.root: print('Resuming Batch: {},  {} Remain'.format(self.batchName, len(self.doLabels)))

        if self.root and self.print and self.printMulti:
            print('\nBatch Progress: ' + str(self.batchName))
            self.bar.display(True)
            sys.stdout.flush()
        elif self.printQuiet:
            self.bar.display(True)
            sys.stdout.flush()

        while len(self.doLabels) > 0:
            rr = self.doLabels.pop(0)
            self.rAxisMain.append(rr)
            self.zAxisMain.append(rr-1)
            thisBatch = self.batch.pop(0)
            try:
                self.count += 1
            except:
                self.count = 1

            if self.root and self.printMulti:
                # print('\n\n\n--' + self.xlabel +' = ' + str(ind) + ': [' + str(self.count) + '/' + str(self.Nb) + ']--')
                # print('\n\n\n--{} = {}: [{}/{}]--'.format(self.xlabel, ind, self.count, self.Nb))

                print('\n\n--{} = {}: {} Lines/Env--'.format(self.xlabel, rr, self.Nrot))

            N = self.N

            thisSim = multisim(thisBatch, self.env, N, printOut=self.printMulti, printSim=self.printSim,
                               timeAx=self.timeAx, printQuiet=self.printQuiet)

            comm.barrier()

            self.collectVars(thisSim)

            if self.root or self.allSave:
                if self.print:
                    if self.printMulti: print('\n\nBatch Progress: ' + str(self.batchName))
                    self.bar.increment()
                    self.bar.display(True)
                if self.firstRunEver:
                    self.setFirstPoint()
                    self.firstRunEver = False

            if self.printQuiet:
                self.bar.increment()
                self.bar.display(True)
            comm.barrier()
            if self.root or self.allSave:
                self.save(printout=self.print)
                sys.stdout.flush()

    def finish(self):
        if self.root or self.allSave:
            self.doStats()

            if self.complete is False:
                self.completeTime = time.asctime()
                self.complete = True

            if self.print or self.allSave:
                print('\nBatch Complete: {}'.format(self.batchName))
                self.showData()
                print('Finished on {}'.format(self.completeTime))

            self.save()


    def stop(self):
        comm = MPI.COMM_WORLD
        comm.barrier()
        sys.stdout.flush()
        print("slave {} reporting".format(self.rank))
        sys.stdout.flush()
        import pdb
        pdb.set_trace()

    def setFirstPoint(self):
        self.copyPoint = self.sims[0].sims[0].sims[0]

    def initLists(self):
        self.sims = []
        self.profilessC = []
        self.intensitiessC = []
        self.profilessR = []
        self.intensitiessR = []
        self.indicess = []

        self.pBss = []
        self.urProjss = []
        self.rmsProjss = []
        self.temProjss = []

        self.makeStrings()

    def deleteEnvs(self, thisSim):

        if hasattr(thisSim, 'env'):
            del thisSim.env
        for sim in thisSim.sims:
            if hasattr(sim, 'env'):
                del sim.env
            for sm in sim.sims:
                if hasattr(sm, 'env'):
                    del sm.env
        return thisSim

    def collectVars(self, thisSim):
        thisSim = self.deleteEnvs(thisSim)
        if multisim.keepAll:
            self.sims.append(thisSim)
        else:
            self.sims = [thisSim]

        self.profilessC.append(thisSim.profilesC)
        self.intensitiessC.append(thisSim.intensitiesC)
        self.profilessR.append(thisSim.profilesR)
        self.intensitiessR.append(thisSim.intensitiesR)

        self.indicess.append(thisSim.indices)
        self.pBss.append(thisSim.pBs)
        self.urProjss.append(thisSim.urProjs)
        self.rmsProjss.append(thisSim.rmsProjs)
        self.temProjss.append(thisSim.temProjs)

    def findRank(self):
        """Discover and record this PU's rank"""
        comm = MPI.COMM_WORLD
        self.rank = comm.Get_rank()
        self.root = self.rank == 0

    ##  Statistics  ##############################################################

    def doStats(self, force=False, save=True):
        """Do the statistics for the whole batch and plot."""
        if self.root or self.allSave:
            if not self.statsDone or self.redoStats or force:
                self.makePSF()
                self.__findBatchStats()
                self.moranFitting()
                self.calcFfiles()
                self.doPrediction()
            if save: self.save(printout=True)

    def doPrediction(self):
        for ion in self.ions:
            self.makeVrms(ion)

    def findProfileStats(self, profile, ion):
        """Analyze a single profile and return a list of the statistics"""

        def gauss_function(x, a, x0, sigma, b):
            return a * np.exp(-(x - x0) ** 2 / (2 * sigma ** 2)) + b

        # Convolve with PSF and then deconvolve again
        if self.usePsf: profileCon, profileDecon = self.conDeconProfile(profile, ion)

        # Use the moment method to get good initial guesses
        p0 = self.findMomentStats(profile, ion)

        try:
            # Fit gaussians to the lines

            poptRaw, pcovRaw = curve_fit(gauss_function, ion['lamAx'], profile, p0=p0)

            ampRaw = np.abs(poptRaw[0])
            muRaw = np.abs(poptRaw[1])
            sigmaRaw = np.abs(poptRaw[2])
            bRaw = np.abs(poptRaw[3])
            perrRaw = np.sqrt(np.diag(pcovRaw))  # one standard deviation errors

            if self.usePsf:
                poptCon, pcovCon = curve_fit(gauss_function, ion['lamAx'], profileCon, p0=p0)
                poptDecon, pcovDecon = curve_fit(gauss_function, ion['lamAx'], profileDecon, p0=p0)
                ampCon = np.abs(poptCon[0])
                muCon = np.abs(poptCon[1])
                sigmaCon = np.abs(poptCon[2])
                bCon = np.abs(poptCon[3])
                perrCon = np.sqrt(np.diag(pcovCon))

                ampDecon = np.abs(poptDecon[0])
                muDecon = np.abs(poptDecon[1])
                sigmaDecon = np.abs(poptDecon[2])
                bDecon = np.abs(poptDecon[3])
                perrDecon = np.sqrt(np.diag(pcovDecon))

        except (RuntimeError, ValueError):
            return [np.NaN, np.NaN, np.NaN, np.NaN, np.NaN, np.NaN, np.NaN]

        # Subtract the Point Spread Width in quadrature
        if self.usePsf: sigmaSubtract = np.sqrt(np.abs(sigmaCon ** 2 - ion['psfSig_e'] ** 2))  # Subtract off the PSF width

        # Plot the fits
        # if self.plotFits and self.binCheck:  # ion['II'] < self.maxFitPlot:
        #
        #     plotax = ion['lamAx'] - ion['lam00']
        #     fig, ax = plt.subplots()
        #     ax1 = ax
        #     ax2 = ax1
        #
        #     fullint = sum(profile)
        #
        #     ion['II'] += 1
        #
        #     fig.suptitle(ion['lineString'])
        #     fig.canvas.set_window_title('{} second'.format(len(self.timeAx)))
        #
        #     ax1.plot(plotax, profile / fullint, "g-", label="Raw")
        #     ax2.plot(plotax, gauss_function(plotax, ampRaw / fullint, muRaw - ion['lam00'], sigmaRaw, bRaw), 'g.:',
        #              label=
        #              "Raw Fit: {:.4} km/s".format(self.std2V(sigmaRaw, ion)))
        #
        #     # plt.plot(self.lamAx, profileCon, "b", label = "Convolved")
        #     # plt.plot(self.lamAx, gauss_function(self.lamAx, ampCon, muCon, sigmaCon, bCon), 'b.:', label =
        #     #         "Conv Fit: {:.4} km/s".format(self.std2V(sigmaCon)))
        #
        #     # plt.plot(self.lamAx, gauss_function(self.lamAx, ampCon, muCon, sigmaSubtract, bCon), 'c.:', label =
        #     #         "Subtraction: {:.4} km/s".format(self.std2V(np.abs(sigmaSubtract))))
        #     ax2.plot(plotax, gauss_function(plotax, ampRaw / fullint, muCon - ion['lam00'], sigmaSubtract, bRaw), 'm.:',
        #              label=
        #              "Subtraction {:.4} km/s".format(self.std2V(np.abs(sigmaSubtract), ion)))
        #
        #     # plt.plot(self.lamAx, profileDecon, "r--", label = "Deconvolved")
        #     # plt.plot(self.lamAx, gauss_function(self.lamAx, ampDecon, muDecon, sigmaDecon, bDecon), 'r.:', label =
        #     #         "Deconvolved Fit: {:.4} km/s".format(self.std2V(sigmaDecon)))
        #     ax2.set_xlim([-2, 2])
        #     ax2.set_ylim([0, 0.03])
        #     # grid.maximizePlot()
        #     # plt.yscale('log')
        #     ax2.set_title("A Line at b = {}".format(self.impact))
        #     ax2.set_xlabel('Wavelength (A)')
        #     ax2.set_ylabel('Intensity (Arb. Units)')
        #     ax2.legend()
        #
        #     plt.show(True)
        #
        # if self.plotbinFitsNow and False:
        #     fig = ion['binfig']
        #     axarray = ion['binax']
        #     status = ion['binstatus']
        #     ax1 = axarray[status]
        #     ax2 = axarray[status + 2]
        #
        #     fig.suptitle(ion['lineString'])
        #     ax1.plot(ion['lamAx'], profile / np.sum(profile), "g", label="Raw")
        #
        #     fitprofile = gauss_function(ion['lamAx'], ampRaw, muCon, sigmaSubtract, bRaw)
        #     normprofile = fitprofile / np.sum(fitprofile)
        #     ax2.plot(ion['lamAx'], normprofile, 'm', label=
        #     "Subtraction {:.4} km/s".format(self.std2V(np.abs(sigmaSubtract), ion)))


        if self.doLinePlot and self.impact > self.plotheight:
            fig, ax = plt.subplots(1,1)

            ax.plot(ion['lamAx'], profile, label='Raw')
            # ax.plot(ion['lamAx'], profileCon, label='Convolved')
            # ax.plot(ion['lamAx'], gauss_function(ion['lamAx'], ampRaw, muRaw, sigmaRaw, bRaw), label='Raw Fit')
            ax.plot(ion['lamAx'], gauss_function(ion['lamAx'], ampRaw, muRaw, sigmaSubtract, bCon), label='Degraded Fit')
            ax.set_title("{} at b = {}".format(ion['lineString'], self.impact))
            ax.legend()
            savePath = '{}/{}_{}/'.format(self.linePath, ion['ionString'], ion['lam0'])
            if not os.path.exists(savePath):
                os.makedirs(savePath)
            filePath = '{}/{:0.4}.png'.format(savePath, self.impact)
            plt.savefig(filePath)
            plt.close(fig)


        # Select which of the methods gets output
        if self.usePsf:
            if self.reconType.casefold() in 'Deconvolution'.casefold():
                self.reconType = 'Deconvolution'
                ampOut, muOut, sigOut, perrOut = ampDecon, muDecon, sigmaDecon, perrDecon
            elif self.reconType.casefold() in 'Subtraction'.casefold():
                self.reconType = 'Subtraction'
                ampOut, muOut, sigOut, perrOut = ampCon, muCon, sigmaSubtract, perrCon
            elif self.reconType.casefold() in 'None'.casefold():
                self.reconType = 'None'
                ampOut, muOut, sigOut, perrOut = ampCon, muCon, sigmaCon, perrCon
            else:
                raise Exception('Undefined Reconstruction Type')
        else:
            self.reconType = 'N/A'
            ampOut, muOut, sigOut, perrOut = ampRaw, muRaw, sigmaRaw, perrRaw

        # Check the reconstruction against the raw fit
        ratio = self.std2V(sigOut, ion) / self.std2V(sigmaRaw, ion)

        return [ampOut, muOut, sigOut, 0, 0, perrOut, ratio]

    def makePSF(self):
        """Do all the things for the PSF that only have to happen once per run"""

        def gauss_function(x, a, x0, sigma, b): return a * np.exp(-(x - x0) ** 2 / (2 * sigma ** 2)) + b

        for ion in self.ions:
            lamRez = np.diff(ion['lamAx'])[0]
            ion['psfSig_e'] = self.FWHM_to_e(ion['psfsig_FW'])
            # ion['psfSig_e'] = self.FWHM_to_e(ion['lam00']/self.spectralResolution)
            psfPix = int(np.ceil(ion['psfSig_e'] / lamRez))
            ion['psf'] = gauss_function(ion['lamAx'], 1, ion['lam00'], ion['psfSig_e'], 0)

            pass

    def FWHM_to_e(self, sig):
        return sig / 2 * np.sqrt(np.log(2))

    def e_to_FWHM(self, sig):
        return sig * 2 * np.sqrt(np.log(2))

    def conDeconProfile(self, profile, ion):
        """Convolve a profile and deconvolve it again, return both. """
        profLen = len(profile)

        buffer = 0.1

        # Pad the profile and the psf, both for resolution and for edge effects
        padd = 1000  # self.psfPix
        psfPad = np.pad(ion['psf'], padd, 'constant')
        profilePad = np.pad(profile, (0, 2 * padd), 'constant')

        # Shift the PSF to be correct in frequency space and normalize it
        psfShift = np.fft.fftshift(psfPad)
        psfShift = psfShift / np.sum(psfShift)

        # Transform the PSF
        psFFT = np.fft.fft(psfShift)

        # Convolve
        proFFT = np.fft.fft(profilePad)
        convFFT = proFFT * psFFT
        profileCon = np.fft.ifft(convFFT)

        # Deconvolve
        proConFFT = np.fft.fft(profileCon)
        dconvFFT = proConFFT / (psFFT + buffer)
        profileDecon = np.fft.ifft(dconvFFT)

        if self.plotFits and ion['II'] < self.maxFitPlot and False:
            plt.figure()
            plt.plot(np.fft.ifftshift(psFFT), label='psf')
            plt.plot(np.fft.ifftshift(proFFT), ':', label='profile')
            plt.plot(np.fft.ifftshift(convFFT), label='conv')
            plt.plot(np.fft.ifftshift(dconvFFT), label='dconv')
            plt.legend()
            grid.maximizePlot()
            plt.show(False)

        # psf = self.con.Gaussian1DKernel(pix)
        # padleft = (len(profile) - len(self.psf.array)) // 2
        # padright = padleft + (len(profile) - len(self.psf.array)) % 2
        # psfLong = np.pad(self.psf.array, (padleft, padright), mode='constant')
        ##psfLong = np.fft.fftshift(psfLong)
        # diff =  self.lamRez
        # padd = int(np.ceil(angSig/diff))

        # profileCon = self.con.convolve(profilePad, np.fft.ifftshift(psfShift[:-1]), boundary='extend', normalize_kernel = True)
        # profileDecon, remainder = scisignal.deconvolve(profileCon, psfShift)
        # padleft = (len(profile) - len(profileDecon)) // 2
        # padright = padleft + (len(profile) - len(profileDecon)) % 2
        # profileDecon = np.pad(profileDecon, (padleft, padright), mode='constant')
        # plt.plot(self.env.lamAx, profile, label="raw")
        # plt.plot(self.env.lamAx, profileCon[0:profLen], label="con")
        # plt.plot(self.env.lamAx, profileDecon[0:profLen], ":", label="decon")
        ##plt.plot(self.env.lamAx, remainder[0:profLen], ":", label="rem")
        # plt.legend()
        # plt.figure()
        # plt.plot(prcFFT)
        # plt.show()

        return np.abs(profileCon[0:profLen]), np.abs(profileDecon[0:profLen])

    def findMomentStats(self, profile, ion):
        # Finds the moment statistics of a profile

        maxMoment = 5
        moment = np.zeros(maxMoment)
        for mm in np.arange(maxMoment):
            moment[mm] = np.dot(profile, ion['lamAx'] ** mm)

        powerM = moment[0]
        muM = moment[1] / moment[0]
        sigmaM = np.sqrt(moment[2] / moment[0] - (moment[1] / moment[0]) ** 2)
        skewM = (moment[3] / moment[0] - 3 * muM * sigmaM ** 2 - muM ** 3) / sigmaM ** 3
        kurtM = (moment[4] / moment[0] - 4 * muM * moment[3] / moment[
            0] + 6 * muM ** 2 * sigmaM ** 2 + 3 * muM ** 4) / sigmaM ** 4 - 3
        ampM = powerM / (np.sqrt(2 * np.pi) * sigmaM) / len(ion['lamAx'])

        return [ampM, muM, sigmaM, 0]

    def __findSampleStats(self):
        # Finds the mean and varience of each of the statistics for each multisim
        nIon = len(self.ions)
        self.stat = []
        self.statV = []
        self.allStd = []
        self.binStdV = []
        self.binStdVsig = []
        self.allRatio = []
        for ii in np.arange(nIon):
            self.stat.append([[[], []], [[], []], [[], []], [[], []], [[], []], [[], []]])
            self.statV.append([[[], []], [[], []], [[], []], [[], []], [[], []], [[], []]])
            self.allStd.append([])
            self.binStdV.append([])
            self.binStdVsig.append([])
            self.allRatio.append([])

        for simStats, impact, binStats in zip(self.impactStats, self.impacts, self.binStats):
            # For Each Impact Parameter

            for ion, binIon, idx in zip(self.ions, binStats, np.arange(nIon)):
                # For Each Ion
                ion['idx'] = idx

                # Collect all of the measurements
                allAmp = [x[idx][0] for x in simStats if not np.isnan(x[idx][0])]
                allMean = [x[idx][1] for x in simStats if not np.isnan(x[idx][1])]
                allMeanC = [x[idx][1] - ion['lam00'] for x in simStats if not np.isnan(x[idx][1])]
                allStd = [x[idx][2] for x in simStats if not np.isnan(x[idx][2])]
                allSkew = [x[idx][3] for x in simStats if not np.isnan(x[idx][3])]
                allKurt = [x[idx][4] for x in simStats if not np.isnan(x[idx][4])]
                allRatio = [x[idx][6] for x in simStats if not np.isnan(x[idx][6])]

                # Wavelength Units
                self.assignStat(idx, 0, allAmp)
                self.assignStat(idx, 1, allMeanC)
                self.assignStat(idx, 2, allStd)
                self.assignStat(idx, 3, allSkew)
                self.assignStat(idx, 4, allKurt)

                # Velocity Units
                self.assignStatV(idx, 0, allAmp)
                self.assignStatV(idx, 3, allSkew)
                self.assignStatV(idx, 4, allKurt)

                # I think that these functions do what they are supposed to.
                mean1 = self.__mean2V(np.mean(allMean), ion)
                std1 = np.std([self.__mean2V(x, ion) for x in allMean])
                self.assignStatV2(idx, 1, mean1, std1)

                self.allStd[idx].append([self.std2V(x, ion) for x in allStd])
                mean2 = self.std2V(np.mean(allStd), ion)
                std2 = self.std2V(np.std(allStd), ion)
                self.assignStatV2(idx, 2, mean2, std2)

                # Collect the binned version of the profile stats
                try:
                    s1 = binIon[2]
                    s2 = binIon[5][2]
                except:
                    s1, s2 = np.nan, np.nan

                self.binStdV[idx].append(self.std2V(s1, ion))
                self.binStdVsig[idx].append(self.std2V(s2, ion))

                self.allRatio[idx].append(allRatio)
                self.assignStat(idx, 5, allRatio)
                self.assignStatV(idx, 5, allRatio)

    def assignStat(self, idx, n, var):
        self.stat[idx][n][0].append(np.mean(var))
        self.stat[idx][n][1].append(np.std(var))

    def assignStatV(self, idx, n, var):
        self.statV[idx][n][0].append(np.mean(var))
        self.statV[idx][n][1].append(np.std(var))

    def assignStatV2(self, idx, n, mean, std):
        self.statV[idx][n][0].append(mean)
        self.statV[idx][n][1].append(std)

    def __mean2V(self, mean, ion):
        # Finds the redshift velocity of a wavelength shifted from lam0
        return self.env.cm2km((self.env.ang2cm(mean) - self.env.ang2cm(ion['lam00'])) * self.env.c /
                              (self.env.ang2cm(ion['lam00'])))

    def std2V(self, std, ion):
        return np.sqrt(2) * self.env.cm2km(self.env.c) * (std / ion['lam00']) #km/s

    def __findBatchStats(self):
        """Find the statistics of all of the profiles in all of the multisims"""
        self.impactStats = []
        self.binStats = []
        self.intensityStats = []
        print("\nFitting Profiles...")
        bar = pb.ProgressBar(len(self.profilessC))
        bar.display()

        # for ion in self.ions:
        #     plt.close(ion['binfig'])


        # if self.plotbinFits and False:
        #     #Create a 2x2 figure for each ion
        #     for ion in self.ions:
        #         ion['binfig'], binax = plt.subplots(2, 2, sharex=True)
        #         ion['binax'] = binax.flatten()
        #         titles = ['Binned Line', 'All Lines', 'Binned Fit', 'All Fits']
        #         for ind, ax in enumerate(binax.flatten()):
        #             ax.set_title(titles[ind])

        self.plotbinFitsNow = False

        for impProfilesC, impProfilesR, impact in zip(self.profilessC, self.profilessR, self.rAxisMain):
            # For each impact parameter
            self.impact = impact

            # # Plot stuff
            # for ion in self.ions:
            #     ion['II'] = 0 if impact > self.plotheight else 1
            # self.plotbinFitsNow = True if impact > self.plotheight and self.plotbinFits else False

            # Find Statistics
            impProfilesS = self.mergeImpProfs(impProfilesC,
                                              impProfilesR)  # Sum up the collisional and resonant componants
            self.impactStats.append(self.__findSimStats(impProfilesS))  # Find statistics for each line
            self.binStats.append(self.__findStackStats(impProfilesS))  # Find statistics for binned lines
            self.intensityStats.append(
                self.__findIntensityStats(impProfilesC, impProfilesR))  # Find statistics for binned lines

            # # Plot Stuff
            # if impact > self.plotheight and self.plotbinFits:
            #     for ion in self.ions:
            #         ion['binfig'].show()
            bar.increment()
            bar.display()
        bar.display(force=True)
        self.__findSampleStats()
        self.assignIntensities()
        self.statsDone = True

        # if self.plotbinFits:
        #     pass
            # for ion in self.ions:
            #    plt.close(ion['binfig'])

    def __findStackStats(self, impProfiles):
        """Stack all the profiles in a list and then get statistics"""

        stacks = []
        for ion in self.ions:
            ion['binstatus'] = 0
            stacks.append(np.zeros_like(ion['lamAx']))

        for profileBundle in impProfiles:
            for ionLine, stack in zip(profileBundle, stacks):
                stack += ionLine  # / np.sum(ionLine)

        self.binCheck = True
        out = self.__findIonStats(stacks)
        self.binCheck = False
        return out

    def __findSimStats(self, impProfiles):
        """Find the statistics of all profiles in a given list"""
        simStats = []
        self.binCheck = False
        for ion in self.ions:
            ion['binstatus'] = 1
        for profileBundle in impProfiles:
            simStats.append(self.__findIonStats(profileBundle))
        return simStats

    def __findIonStats(self, profileBundle):
        """Finds the stats for each ion in a given LOS"""
        ionStats = []
        for ion, ionLine in zip(self.ions, profileBundle):
            ionStats.append(self.findProfileStats(ionLine, ion))
        if self.doLinePlot: plt.show()
        return ionStats

    def __findIntensityStats(self, impProfilesC, impProfilesR):
        """cant do it"""
        nions = len(self.ions)
        Cbucket = np.zeros(nions)
        Rbucket = np.zeros(nions)
        ii = 0

        returnlist = []
        for bundleC, bundleR in zip(impProfilesC, impProfilesR):
            # For each LOS
            ii += 1
            jj = 0
            for ion, profC, profR in zip(self.ions, bundleC, bundleR):
                dlam = np.mean(np.diff(ion['lamAx']))
                # For each ion
                Cbucket[jj] += np.sum(profC) * dlam
                Rbucket[jj] += np.sum(profR) * dlam
                jj += 1

        avgC = Cbucket / ii
        avgR = Rbucket / ii
        thisResult = (avgC, avgR)

        return thisResult  # a list for each ion, the two intensities

    def mergeImpProfs(self, impProfilesC, impProfilesR):
        # Sum two different boxes of profiles
        A = np.asarray(impProfilesC)
        B = np.asarray(impProfilesR)
        C = np.zeros_like(impProfilesC)

        if self.resonant and self.collisional:
            # if both, sum
            for ii in np.arange(len(A)):
                for jj in np.arange(len(A[0])):
                    C[ii][jj] = A[ii][jj] + B[ii][jj]
            return C.tolist()
        elif self.collisional:
            return A.tolist()
        elif self.resonant:
            return B.tolist()
        else:
            return C.tolist()

    def plotProfiles(self, max):
        if max is not None:
            for profiles, impact in zip(self.profiless, self.rAxisMain):
                plt.figure()
                plt.title('Impact: ' + str(impact))
                plt.xlabel('Wavelength')
                count = 0
                for profile in profiles:
                    if count < max:
                        plt.plot(self.env.lamAx, profile)
                        count += 1
                plt.show()

    def plotProfTogether(self, average=False, norm=False, log=False):
        plt.figure()
        plt.title('Profiles vs Impact')
        plt.xlabel('Wavelength')
        plt.ylabel('Intensity')

        for profiles, impact in zip(self.profiless, self.rAxisMain):
            profsum = np.zeros_like(profiles[0])
            count = 0
            for profile in profiles:
                if norm: profile /= np.amax(profile)
                if average:
                    profsum += profile
                    count += 1
                else:
                    plt.plot(self.env.lamAx, profile, label=impact)
                    break
            if average:
                profsum /= count
                plt.plot(self.env.lamAx, profile, label=impact)
        if log: plt.yscale('log')
        plt.legend()
        plt.show()

    def plotStats(self):
        f, axArray = plt.subplots(3, 1, sharex=True)
        mm = 0
        titles = ['amp', 'mean', 'sigma']
        ylabels = ['', 'Angstroms', 'Angstroms']
        for ax in axArray:
            if mm == 0: ax.set_yscale('log')
            ax.errorbar(self.impacts, self.stat[mm][0], yerr=self.stat[mm][1], fmt='o')
            ax.set_title(titles[mm])
            ax.set_ylabel(ylabels[mm])
            mm += 1
            ax.autoscale(tight=False)
        ax.set_xlabel(self.xlabel)
        plt.show(False)

    def chiTest(self, ion):

        # self.hahnMids = np.interp(self.env.hahnAbs, self.histlabels, self.medians)
        # self.hahnMeans = np.interp(self.env.hahnAbs, self.histlabels, self.lineWidths)
        # self.hahnMidErrors = np.interp(self.env.hahnAbs, self.histlabels, self.lineWidthErrors)

        self.chi_bin = 0
        self.chi_mean = 0

        N = 0
        locs, width, error = self.ionEffVelocity(ion)
        for expectedWidth, binWidth, binError, meanWidth, meanError in zip(ion['expectedRms'], width, error, self.lineWidths,self.lineWidthErrors):
            N += 1
            self.chi_bin += (binWidth - expectedWidth) ** 2 / (binError * binError)
            self.chi_mean += (meanWidth - expectedWidth) ** 2 / (meanError * meanError)

        self.rChi_bin = self.chi_bin / N
        self.rChi_mean = self.chi_mean / N

        # height = 0.9
        # left = 0.65 + 0.09
        # shift = 0.1
        # plt.figtext(left + shift, height + 0.04, "Fit to the Mean")
        # plt.figtext(left + shift, height + 0.02, "Chi2 = {:0.3f}".format(self.chi_mean))
        # plt.figtext(left + shift, height, "Chi2_R = {:0.3f}".format(self.rChi_mean))

    def getLabels(self):
        try:
            labels = np.asarray(self.rAxisMain)
        except:
            labels = np.arange(len(self.profiles))
            doRms = False
        return labels

    def saveFile(self, batchName):
        """Save the batch to file safely"""

        tempPath = os.path.abspath("../dat/batches/{}_temp.batch".format(batchName))
        finalPath = os.path.abspath("../dat/batches/{}.batch".format(batchName))

        with open(tempPath, 'wb') as output:
            pickle.dump(self, output, pickle.HIGHEST_PROTOCOL)

        if os.path.exists(finalPath):
            os.remove(finalPath)
        os.rename(tempPath, finalPath)

    def deleteFile(self, batchName):
        finalPath = os.path.abspath("../dat/batches/{}.batch".format(batchName))
        if os.path.exists(finalPath):
            os.remove(finalPath)

    def rename(self, newName):
        oldName = self.batchName
        self.batchName = newName
        self.save()
        self.deleteFile(oldName)
        print("Batch {} renamed to {}".format(oldName, newName))

    def save(self, batchName=None, printout=False):
        """Handles saving the batch"""

        if batchName is None:
            batchName = self.batchName

        stuff = self.removeEnv()
        self.saveFile(batchName)
        self.returnEnv(*stuff)

        if printout: print('\nFile Saved')

    def removeEnv(self):
        """Delete the environment from the object"""
        try:
            sims = self.sims
            env = self.env
        except:
            sims = []
            env = []

        # Delete it from self
        if not self.saveSims:
            self.sims = []
        self.env = []

        return sims, env

    def returnEnv(self, sims, env):
        """ Restore data to batch """
        self.sims = sims
        self.env = env

    def reloadEnv(self, env):
        self.env = env

    def show(self):
        """Print all properties and values except statistics"""
        myVars = vars(self)
        print("\nBatch Properties\n")
        for ii in sorted(myVars.keys()):
            if not "stat" in ii.lower():
                print(ii, " : ", myVars[ii])

    def showAll(self):
        """Print all properties and values"""
        myVars = vars(self)
        print("\nBatch Properties\n")
        for ii in sorted(myVars.keys()):
            print(ii, " : ", myVars[ii])

    def doOnePB(self):
        pBs = np.asarray(self.pBss[-1])
        self.pBavg = np.average(pBs)
        self.pBstd = np.std(pBs)

    def write_roman(self, num):

        roman = OrderedDict()
        roman[1000] = "M"
        roman[900] = "CM"
        roman[500] = "D"
        roman[400] = "CD"
        roman[100] = "C"
        roman[90] = "XC"
        roman[50] = "L"
        roman[40] = "XL"
        roman[10] = "X"
        roman[9] = "IX"
        roman[5] = "V"
        roman[4] = "IV"
        roman[1] = "I"

        def roman_num(num):
            for r in roman.keys():
                x, y = divmod(num, r)
                yield roman[r] * x
                num -= (r * x)
                if num > 0:
                    roman_num(num)
                else:
                    break

        return "".join([a for a in roman_num(num)])

    def calcFfiles(self):
        # Calculate the f parameters
        # print("\nCalculating f Files:", end='', flush=True)

        self.f1_new = []
        self.f2_new = []
        self.f3_new = []
        self.fr_new = []

        for urProjs, rmsProjs, temProjs, b in zip(self.urProjss, self.rmsProjss, self.temProjss,
                                                  self.rAxisMain):
            # Get the Average (of all los at this impact) Projected Values
            urProj = np.average(urProjs)
            rmsProj = np.average(rmsProjs)
            temProj = np.average(temProjs)

            # Get the Plane of the Sky Values
            pTem = self.env.interp_T(b)
            pUr = self.env.interp_ur(b)
            pRms = self.env.interp_vrms(b)

            # Find the fraction of the POS values
            urProjFrac = urProj / pUr
            rmsProjFrac = rmsProj / pRms
            temProjFrac = temProj / pTem

            # Store the info
            # print("{:0.04} ur: {:0.04}, rms: {:0.04}, tem: {:0.04}".format(b, urProjFrac, rmsProjFrac, temProjFrac), flush=True)
            self.fr_new.append(b)
            self.f1_new.append(urProjFrac)
            self.f2_new.append(rmsProjFrac)
            self.f3_new.append(temProjFrac)
        # print('done')

    def plotFfiles(self):
        '''Plot the new F functions compared to the ones in env'''
        fig, ax = plt.subplots()
        newZ = np.asarray(self.fr_new) - 1
        ax.plot(newZ, self.f1_new, label='F1 - wind - 5k New', c='r')
        ax.plot(newZ, self.f2_new, label='F2 - waves - 5k New', c='g')
        ax.plot(newZ, self.f3_new, label='F3 - temp - 5k New', c='b')

        oldZ = np.asarray(self.env.fr) -1
        ax.plot(oldZ, self.env.f1_raw, label='F1 - 5k',c='r', ls=':')
        ax.plot(oldZ, self.env.f2_raw, label='F2 - 5k',c='g', ls=':')
        ax.plot(oldZ, self.env.f3_raw, label='F3 - 5k',c='b', ls=':')

        plt.legend()
        ax.set_yscale('linear')
        ax.set_xscale('log')
        plt.axhline(1, color='k')
        plt.show()

    def storeFfiles(self, name='default'):
        file = os.path.normpath("{}/f_{}.txt".format(self.env.datFolder, name))

        with open(file, 'w') as fout:
            for ii, b in enumerate(self.fr_new):
                fout.write('{}    {}    {}    {}\n'.format(b, self.f1_new[ii], self.f2_new[ii], self.f3_new[ii]))
                fout.flush()

    def storeFfiles_old(self, name='default'):
        folder = self.env.datFolder
        file1 = os.path.normpath(folder + '/f1_' + name + '.txt')
        file2 = os.path.normpath(folder + '/f2_' + name + '.txt')
        file3 = os.path.normpath(folder + '/f3_' + name + '.txt')

        with open(file1, 'w') as f1out:
            with open(file2, 'w') as f2out:
                with open(file3, 'w') as f3out:
                    for ii,b in enumerate(self.fr_new):
                        f1out.write('{}   {}\n'.format(b, self.f1_new[ii]))
                        f1out.flush()
                        f2out.write('{}   {}\n'.format(b, self.f2_new[ii]))
                        f2out.flush()
                        f3out.write('{}   {}\n'.format(b, self.f3_new[ii]))
                        f3out.flush()

    def updateBatch(self):
        self.reassignColors()
        self.makeStrings()
        self.assignIntensities()
        try:
            self.rAxisMain = self.doneLabels
            self.zAxisMain = [rr - 1 for rr in self.rAxisMain]
        except: pass
        self.save()

    def reassignColors(self):
        self.env.assignColors(self.ions)

    def makeStrings(self):
        for ii, ion in enumerate(self.ions):
            ion['lineString'] = self.ionLineLabel(ion)
            # ion['ionNum'] = ii

    def getAx(self, ax):
        if not ax:
            fig, ax = plt.subplots(1, 1, True)
            show = True
        else:
            fig = ax.get_figure()
            show = False
        return fig, ax, show

    ## Main Plots ########################################################################
    def plot(self):
        if self.showInfo: self.showData()
        if self.pIon: self.ionPlot()
        if self.pMass: self.plotAsTemperature1()
        if self.pMass2: self.plotAsTemperature2()
        if self.pProportion: self.plotStack(self.ions[self.plotIon])
        if self.pWidth: self.plotMultiWidth()
        if self.pPB: self.plotPB()
        if self.pIntRat: self.plotIntRatClean()
        if self.plotF: self.plotFfiles()
        plt.show(block=True)

    def showData(self):
        print("Simulated {} ions, at {} impacts between {} and {}".format(len(self.ions), self.count, min(self.rAxisMain), max(self.rAxisMain)))

    def plotLineIntensity(self, ax0=None, ionNums=False, ls='-'):
        """Plot the total intensity as a function of height for given ions"""
        fig, ax, show = self.getAx(ax0)

        if ionNums == False:
            ionNums = [1,2]

        ionList = [self.ions[ii] for ii in ionNums]
        ionList = self.ions
        for ion in ionList:
            ax.plot(self.zAxisMain, ion['rInt'], label=ion['fullString'], c=ion['c'], ls=ls)

        self.env.solarAxis(ax)
        ax.set_yscale('log')

        if show: plt.show()


    def plotLineRatio(self, ax0=None, ionNums=False, **kwargs):
        fig, ax, show = self.getAx(ax0)
        self.assignIntensities()

        if ionNums == False:
            ionNums = [1,2]

        ion0 = self.ions[ionNums[0]]
        ion1 = self.ions[ionNums[1]]

        ratioLabel = "Line Intensity Ratio: {} / {}".format(ion0['lineString'], ion1['lineString'])
        ax.set_title(ratioLabel)

        intensityRatio = ion0['tInt'] / ion1['tInt']

        ax.plot(self.zAxisMain, intensityRatio, **kwargs)
        ax.set_ylabel('Line Ratio')

        if show:
            self.env.solarAxis(ax, 2)
            plt.show()

    def assignIntensities(self):
        # Unpack the integrated intensities into the ion objects.
        C, R = zip(*self.intensityStats)

        Cions = list(zip(*C))
        Rions = list(zip(*R))

        for ion, cint, rint in zip(self.ions, Cions, Rions):
            # For each ion

            #Find total intensity at each height
            tint = [c + r for c, r in zip(cint, rint)]

            #Find the fractions of each type at each height
            cnorm = np.asarray(cint) / np.asarray(tint)
            rnorm = np.asarray(rint) / np.asarray(tint)

            #Store
            ion['cInt'] = np.asarray(cint)
            ion['rInt'] = np.asarray(rint)
            ion['tInt'] = np.asarray(tint)
            ion['cFrac'] = np.asarray(cnorm)
            ion['rFrac'] = np.asarray(rnorm)

    def plotIntRatClean(self, ax0=None, ionNum=False, ls='-', **kwargs):
        """Plot the CvsR proportions"""
        useCollis = True
        useTitle = False
        if not ionNum is False:
            plotOne = True
        else: plotOne = False

        fig, ax0, show = self.getAx(ax0)
        # self.updateBatch()

        if useTitle:
            if useCollis: ax0.set_title('Collisional Component of Spectra')
            else: ax0.set_title('Resonant Component of Spectra')

        ax0.axhline(0.5, c='lightgray', ls=(0,(5,3)), zorder=0, lw=0.5)

        for ii, ion in enumerate(self.ions):
            # For each ion
            if plotOne:
                if ii < ionNum:
                    continue

            if useCollis: toplot = ion['cFrac']
            else: toplot = ion['rFrac']
            thisLabel = self.batchName
            if "FullChop" in thisLabel: thisLabel = "Chop 100"
            ax0.plot(self.zAxisMain, toplot, c=ion['c'], label=thisLabel, ls=ls, **kwargs)
            # ax0.set_title(self.ionLineLabel(ion))
            if plotOne: break

        ax0.set_xscale('log')
        ax0.set_ylim((0,1))
        ax0.set_xlim((0.01,10))


        if show:
            fig.set_size_inches((5, 5))
            self.env.solarAxis(ax0)
            plt.tight_layout()
            plt.show()


    def plotPB(self):
        def pbFit(r): return 1e-9 * (1570 * r ** -11.1 + 6.75 * r ** -3.42)

        # sigmaT = 6.65e-25
        # coeff = 3/16*sigmaT

        fig, ax = plt.subplots()

        pbAvg = []
        pbStd = []
        fits = []
        for impact, pbs in zip(self.rAxisMain, self.pBss):
            pbAvg.append(np.mean(pbs))
            pbStd.append(np.std(pbs))

            fits.append(pbFit(impact))

        ax.errorbar(self.rAxisMain, pbAvg, yerr=pbStd, capsize=3, label='Simulated Values')

        plt.plot(self.rAxisMain, [f for f in fits], label='Fit Function')

        ax.set_yscale('log')
        ax.set_ylabel('r / $R_\odot$')
        ax.set_ylabel('pB')
        ax.set_title('Polarization Brightness')
        ax.legend()

        plt.show()

        pass

    def plotStatsV(self):
        """Plot all of the statistics for the whole batch."""
        f, axArray = plt.subplots(5, 1, sharex=True)
        f.canvas.set_window_title('Coronasim')
        doRms = True
        labels = self.getLabels()
        mm = 0
        titles = ['Intensity', 'Mean Redshift', 'Line Width', 'Skew', 'Excess Kurtosis']
        ylabels = ['', 'km/s', 'km/s', '', '']
        # import copy
        # thisBlist = copy.deepcopy(self.Blist)
        try:
            self.completeTime
        except:
            self.completeTime = 'Incomplete Job'
        f.suptitle(str(self.batchName) + ': ' + str(self.completeTime) + '\n Wavelength: ' + str(self.env.lam0) +
                   ' Angstroms\nLines per Impact: ' + str(self.Npt) + '\n Envs: ' + str(self.Nenv) +
                   '; Lines per Env: ' + str(
            self.Nrot) + '\n                                                                      statType = ' + str(
            self.statType))
        for ax in axArray:
            if mm == 0: ax.set_yscale('log')  # Set first plot to log axis
            ax.errorbar(labels, self.statV[mm][0], yerr=self.statV[mm][1], fmt='o')
            if mm == 2 and doRms:  # Plot Vrms
                ax.plot(labels, self.thisV)

                # Put numbers on plot of widths
                for xy in zip(labels, self.statV[mm][0]):
                    ax.annotate('(%.2f)' % float(xy[1]), xy=xy, textcoords='data')
            if mm == 1 or mm == 3 or mm == 4:  # Plot a zero line
                ax.plot(labels, np.zeros_like(labels))
            ax.set_title(titles[mm])
            ax.set_ylabel(ylabels[mm])
            mm += 1
            spread = 0.05
            ax.set_xlim([labels[0] - spread, labels[-1] + spread])  # Get away from the edges
        ax.set_xlabel(self.xlabel)
        grid.maximizePlot()
        plt.show()

    def rmsPlot(self):

        # Get the RMS values out of the braid model
        braidRMS = []
        braidImpacts = np.linspace(1.015, 3, 100)
        for b in braidImpacts:
            braidRMS.append(self.env.interp_vrms(b))

        # Get the RMS values out of coronasim
        maxImpact = 20
        rez = 200
        line = simulate(grid.sightline([3, 0, 0], [maxImpact, 0, 0], coords='Sphere'), self.env, rez, timeAx=[0])
        modelRMS = line.get('vRms')
        modelImpacts = line.get('pPos', 0)

        plt.plot(braidImpacts, [self.env.cm2km(x) for x in braidRMS], label='Braid')
        # print(braidRMS[-6])
        # print(braidImpacts[-6])
        plt.plot(modelImpacts, [self.env.cm2km(x) for x in modelRMS], label='Model')
        plt.legend()
        plt.xlabel('r / $R_{\odot}$')
        plt.ylabel('RMS Amplitude (km/s)')
        plt.title('RMS Wave Amplitude Extrapolation')
        plt.xscale('log')
        plt.show()

    def getLabels(self):
        try:
            labels = np.asarray(self.rAxisMain)
        except:
            labels = np.arange(len(self.profiles))
            doRms = False
        return labels

    def makeVrms(self, ion):
        # self.env.fLoad(self.env.fFile)
        ion['expectedRms'] = []
        ion['V_wind'] = []
        ion['V_waves'] = []
        ion['V_thermal'] = []
        ion['V_nt'] = []
        ion['expectedRms_raw'] = []
        ion['V_wind_raw'] = []
        ion['V_waves_raw'] = []
        ion['V_thermal_raw'] = []
        ion['V_nt_raw'] = []
        self.hahnV = []

        for impact in self.rAxisMain:
            ##Get model values for wind, rms, and temperature in plane of sky at this impact
            pTem = self.env.interp_rx_dat(impact, self.env.T_raw)
            pUr = self.env.interp_rx_dat(impact, self.env.ur_raw) if self.copyPoint.windWasOn else 0
            pRms = self.env.interp_vrms(impact) if self.copyPoint.waveWasOn else 0

            vTh = 2 * self.env.KB * pTem / ion['mIon']

            wind = (self.env.interp_w2_wind(impact) * pUr) ** 2
            waves = (self.env.interp_w2_waves(impact) * pRms) ** 2
            thermal = (self.env.interp_w2_thermal(impact) * vTh) ** 1

            wind_raw = (pUr) ** 2
            waves_raw = (pRms) ** 2
            thermal_raw = (vTh) ** 1

            V = np.sqrt((wind + waves + thermal))
            V_raw = np.sqrt((wind_raw + waves_raw + thermal_raw))

            ion['expectedRms'].append(self.env.cm2km(V))
            ion['V_nt'].append(self.env.cm2km(np.sqrt(wind + waves)))
            ion['V_wind'].append(self.env.cm2km(np.sqrt(wind)))
            ion['V_waves'].append(self.env.cm2km(np.sqrt(waves)))
            ion['V_thermal'].append(self.env.cm2km(np.sqrt(thermal)))

            ion['expectedRms_raw'].append(self.env.cm2km(V_raw))
            ion['V_nt_raw'].append(self.env.cm2km(np.sqrt(wind_raw + waves_raw)))
            ion['V_wind_raw'].append(self.env.cm2km(np.sqrt(wind_raw)))
            ion['V_waves_raw'].append(self.env.cm2km(np.sqrt(waves_raw)))
            ion['V_thermal_raw'].append(self.env.cm2km(np.sqrt(thermal_raw)))

            self.hahnV.append(self.hahnFit(impact))

    def plotExpectations(self, ax, ion, weightFunc):
        """Plots the expected results along with the true results, in velocity space"""

        self.makeVrms(ion)
        rAxis, measurements, error = self.ionEffVelocity(ion)
        zAxis = self.env.r2zAxis(rAxis)

        modified = [mm / weightFunc(rr) for mm, rr in zip(measurements, rAxis)]

        ax.loglog(zAxis, ion['expectedRms_raw'], c=ion['c'], ls='-',  label='Raw Expectation')
        ax.loglog(zAxis, measurements,           c=ion['c'], ls='--', label='Raw Measurement')

        ax.loglog(zAxis, ion['expectedRms'],     c=ion['c'], ls='-.', label='Weighted Expectation')
        ax.loglog(zAxis, modified,               c=ion['c'], ls=':',  label='Weighted Measurement')

        ax.set_ylabel('Velocity (km/s)')
        self.env.solarAxis(ax, 2)
        plt.legend()
        plt.tight_layout()
        # plt.show()

    def plotExpectationsScatter(self, rHeight=4, norm=False):
        """Plot the measured vs expected values at a height, scattered"""
        fig, (ax0) = plt.subplots(1, 1)
        first = True
        for ion in self.ions:
            self.makeVrms(ion)
            rAxis, measurements, error = self.ionEffVelocity(ion)
            zAxis = self.env.r2zAxis(rAxis)
            index = self.env.find_nearest(rAxis, rHeight)
            rrHeight = rAxis[index]

            rawMeasurement = measurements[index]
            rawExpectation = ion['expectedRms_raw'][index]
            weightExpectation = ion['expectedRms'][index]

            if first:
                normMeas = rawMeasurement
                normRaw = rawExpectation
                normWeight = weightExpectation

            if norm:
                rawMeasurement /= normMeas
                rawExpectation /= normRaw
                weightExpectation /= normWeight

            ax0.plot(rawMeasurement, rawExpectation, 'o', c=ion['c'], label='Raw')
            ax0.plot(rawMeasurement, weightExpectation, 'x', c=ion['c'], label='Weighted')
            if first:
                ax0.legend()
                first = False

        ylims = ax0.get_ylim()
        xlims = ax0.get_xlim()
        yy = np.linspace(*ylims)
        xx = yy

        ax0.plot(xx,yy, 'k')

        ax0.set_ylabel('Expectation')
        ax0.set_xlabel('Raw Measurement')
        ax0.set_title('Looking at r = {}'.format(rHeight))

        plt.show()




            # modified = [mm / weightFunc(rr) for mm, rr in zip(measurements, rAxis)]

    # def plotFits(self):



    def plotStack(self, ion):
        self.makeVrms(ion)
        fig, ((ax, ax4), (ax2, ax3)) = plt.subplots(2, 2, sharex=True)
        fig.suptitle(
            '{} {}: {:.2F}$\AA$'.format(ion['eString'].capitalize(), self.write_roman(ion['ionNum']), ion['lam00']))

        xx = self.rAxisMain

        y1 = [x / y for x, y in zip(ion['V_wind'], ion['expectedRms'])]
        y2 = [x / y for x, y in zip(ion['V_waves'], ion['expectedRms'])]
        y3 = [x / y for x, y in zip(ion['V_thermal'], ion['expectedRms'])]
        ax.set_title('Proportion Compared to Total Line Width')
        ax.set_ylabel('Percentage')
        # ax.set_xlabel('Impact Parameter')
        ax.set_ylim([0, 1.05])
        ax.plot(xx, y1, 'b', label='Wind')
        ax.plot(xx, y2, 'g', label='Waves')
        ax.plot(xx, y3, 'r', label='Thermal')
        ax.legend()
        ax.axhline(1, c='k')

        ax2.plot(xx, ion['V_wind'], 'b', label='GW Wind')
        ax2.plot(xx, ion['V_waves'], 'g', label='GW Waves')
        ax2.plot(xx, ion['V_thermal'], 'r', label='GW Thermal')
        ax2.plot(xx, ion['expectedRms'], 'k', label='GW Total')
        ax2.plot(xx, ion['V_wind_raw'], 'b:', label='Wind')
        ax2.plot(xx, ion['V_waves_raw'], 'g:', label='Waves')
        ax2.plot(xx, ion['V_thermal_raw'], 'r:', label='Thermal')
        ax2.plot(xx, ion['expectedRms_raw'], 'k:', label='Total')

        ax2.set_xlabel('Impact Parameter')
        ax2.set_ylabel('Weighted Contribution (km/s)', color='b')
        ax2.tick_params('y', colors='b')
        ax2.set_title('Weighted Velocity Components')
        ax2.legend()

        ax3.plot(xx, self.vel2T(ion, ion['V_wind']), 'b', label='GW Wind')
        ax3.plot(xx, self.vel2T(ion, ion['V_waves']), 'g', label='GW Waves')
        ax3.plot(xx, self.vel2T(ion, ion['V_thermal']), 'r', label='GW Thermal')
        ax3.plot(xx, self.vel2T(ion, ion['expectedRms']), 'k', label='Gw Total')

        ax3.plot(xx, self.vel2T(ion, ion['V_wind_raw']), 'b:', label='Wind')
        ax3.plot(xx, self.vel2T(ion, ion['V_waves_raw']), 'g:', label='Waves')
        ax3.plot(xx, self.vel2T(ion, ion['V_thermal_raw']), 'r:', label='Thermal')
        ax3.plot(xx, self.vel2T(ion, ion['expectedRms_raw']), 'k:', label='Total')

        ax3.tick_params('y', colors='r')
        ax3.set_xlabel('Impact Parameter')
        ax3.set_ylabel('$T_{eff}$', color='r')
        ax3.set_yscale('log')
        ax3.set_title('Effective Temperature Components')
        ax3.legend()

        ax4.set_title('Weighting Functions')
        ax4.plot(xx, [self.env.interp_w2_wind(x) for x in xx], 'b', label='Wind')
        ax4.plot(xx, [self.env.interp_w2_waves(x) for x in xx], 'g', label='Waves')
        ax4.plot(xx, [self.env.interp_w2_thermal(x) for x in xx], 'r', label='Thermal')
        ax4.axhline(1, c='k')
        ax4.legend()

        grid.maximizePlot()

        plt.show(True)

    def ionPlot(self):
        fig, ax1 = plt.subplots()
        for ion in self.ions:
            label = ion['ionString']
            locs, width, error = self.ionEffVelocity(ion)
            ax1.errorbar(locs, width, yerr=error, fmt='-',
                         label=label, capsize=3, color=ion['c'])
        ax1.legend(loc='lower right')
        ax1.set_title('Binned Profile Measurements')
        ax1.set_xlabel('Impact Parameter')
        ax1.set_ylabel('$v_{1/e}$ (km/s)')
        ax1.set_ylim((10,40))
        plt.show(False)

    def weightedPlotTemp(self):
        fig, ax1 = plt.subplots()
        for ion in self.ions:
            label = ion['ionString']
            locs, width, error = self.ionEffVelocity(ion)
            ax1.errorbar(locs, width, yerr=error, fmt='o',
                         label=label, capsize=6)
        ax1.legend()
        ax1.set_title('Binned Profile Measurements')
        ax1.set_xlabel('Impact Parameter')
        ax1.set_ylabel('$v_{1/e}$ (km/s)')
        plt.show(False)

    def moranFitting(self):
        """Do the multi-ion fit method and maybe plot it"""
        try:
            slopes = []
            slopeErrors = []
            intercepts = []
            interceptErrors = []
            self.moranPlotList = []

            kb = 1.38064852e-23  # joules/kelvin = kg(m/s)^2/T
            kbg = kb * 1000  # g(m/s)^2/T
            kbgk = kbg / 1e6  # g(km/s)^2/T

            for impact in np.arange(len(self.rAxisMain)):
                #Do this for every impact
                widthList = []
                widthErrorList = []
                widthSqList = []
                widthSqErrorList = []
                invMassList = []
                massList = []

                # Get all the ion widths at that height
                for ion in self.ions:
                    # Retrieve Values
                    locs, width, error = self.ionEffVelocity(ion)
                    wid = width[impact]  # (km/s)
                    wider = error[impact]  # (km/s)
                    invMass = 2 * kbgk / ion['mIon']  # (km/s)^2 / T

                    # Square with error propagation
                    widthsq = wid ** 2  # (km/s)^2
                    widthsqer = 2 * wid * wider  # (km/s)^2

                    # Store Values
                    widthList.append(wid)
                    widthErrorList.append(wider)
                    widthSqList.append(widthsq)  # (km/s)^2
                    widthSqErrorList.append(widthsqer)  # (km/s)^2
                    invMassList.append(invMass)  # (km/s)^2 / T
                    massList.append(ion['mIon'])

                # Fit a line
                weights = [1 / w for w in widthSqErrorList]
                (slope, intercept), cov = np.polyfit(invMassList, widthSqList, 1, w=weights, cov=True)  # T, (km/s)^2
                (sloper, inter) = np.diag(cov) ** 0.5

                # Save stuff so we can plot later
                self.moranPlotList.append((widthList, widthErrorList, invMassList, slope, intercept))

                # Store Values
                slopes.append(slope / 10 ** 6)  # T
                intercepts.append(intercept ** 0.5)  # km/s
                slopeErrors.append(sloper / 10 ** 6)
                interceptErrors.append(inter ** 0.5)

            self.fitTemps = slopes
            self.fitTempErrors = slopeErrors
            self.nonThermal = intercepts
            self.nonThermalErrors = interceptErrors

        except (np.linalg.LinAlgError, ValueError):
            print('Not enough ions simulated for Moran method')
            self.fitTemps = np.NaN
            self.fitTempErrors = np.NaN
            self.nonThermal = np.NaN
            self.nonThermalErrors = np.NaN

    def moranFitPlot(self, square=True, many=4):
        """Plots the moran fit lines as a function of mass"""

        fig, ax = plt.subplots()

        if square:
            pwr = 2
        else:
            pwr = 1

        # Make the color list
        nLines = len(self.moranPlotList)
        colorShift = 2/nLines
        colorList1 = [(0,0+colorShift*ind,1.-colorShift*ind) for ind in np.arange(nLines/2)]
        colorList2 = [(0+colorShift*ind, 1-colorShift*ind, 0) for ind in np.arange(nLines/2+1)]
        colorList = colorList1 + colorList2


        for impInd, stuff in enumerate(self.moranPlotList):
            # Plot each impact
            (widthList, widthErrorList, invMassList, slope, intercept) = stuff

            if not impInd % many == 0: continue

            color = colorList[impInd] #next(ax._get_lines.prop_cycler)['color']
            # Plot raw velocities
            ax.errorbar(invMassList, [w ** pwr for w in widthList], fmt='o', yerr=widthErrorList,
                        label='{:0.3f}'.format(self.rAxisMain[impInd]), color=color, capsize=3)

            # Plot the fit line
            fitLine = np.polyval((slope, intercept), invMassList) ** (pwr / 2)
            ax.plot(invMassList, fitLine, '-', color=color)

            shortMassList = [0, invMassList[0]]
            fitLine2 = np.polyval((slope, intercept), shortMassList) ** (pwr / 2)
            ax.plot(shortMassList, fitLine2, ':', color=color)

            # Plot the intercept
            ax.plot(0, intercept ** (pwr / 2), '^', color=color)

        # Annotate the ion names
        lastIon = 'xx'
        for xy, ion in zip(zip([m - 2e-5 for m in invMassList], [0 for l in invMassList]), self.ions):
            newIon = ion['eString'][0:2]
            if not newIon == lastIon: ax.annotate('{}'.format(ion['eString']), xy=xy, textcoords='data')
            lastIon = newIon

        # Format Plot and Show
        ax.legend(ncol=3)
        ax.set_xlabel('Inverse Mass (Most Massive to the Left)')
        if pwr == 2:
            ax.set_ylabel('Squared Line Width $(km/s)^2$')
        else:
            ax.set_ylabel("Line Width (km/s)")
        plt.tight_layout()
        plt.show(True)

    def moranPlot(self):

        # Set up Plot
        fig, (ax0, ax1) = plt.subplots(2,1, True)

        rAxis = self.rAxisMain
        zAxis = [r-1 for r in rAxis]

        # Plot the Moran Temperatures
        modFitTemps = [fT / self.env.interp_w2_thermal(rx) for rx, fT in zip(rAxis, self.fitTemps)]
        ax0.errorbar(zAxis, modFitTemps, fmt='ro', yerr=self.fitTempErrors,
                 label='Thermal Component', capsize=2, markersize=4)

        # Plot the Moran Non-Thermal Components
        modFitVelocity = [fT / self.env.interp_w1_wind(rx) for rx, fT in zip(rAxis, self.nonThermal)]
        ax1.errorbar(zAxis, modFitVelocity, fmt='bo', yerr=self.nonThermalErrors,
                 label='Non-Thermal Component', capsize=2, markersize=4)

        # Plot the POS Values for each
        posWind = [self.env.interp_ur(rx)/10**5 for rx in rAxis]
        ax1.plot(zAxis, posWind, 'k:', label='POS Wind', lw=3, zorder=10)

        posTemp = [self.env.interp_T(rx) / 10 ** 6 for rx in rAxis]
        ax0.plot(zAxis, posTemp, 'k:', label='POS Temp', lw=3, zorder=10)

        # Format Plot
        fig.set_size_inches((5,7))

        ax0.set_ylabel('Temperature (K)')
        ax1.set_ylabel('Non-Thermal Velocity (km/s)')
        ax0.set_ylim((0,3))
        ax1.set_yscale('log')
        self.env.solarAxis(ax1)
        plt.tight_layout()
        plt.show()

    def vel2T(self, ion, velocities):
        """Convert velocities to temperatures"""
        const = ion['mIon'] / (2 * self.env.KB) * 10 ** 10
        temps = [v ** 2 * const /10**6 for v in velocities]
        return temps

    def ionEffVelocity(self, ion):
        '''Returns the Effective velocities of an input ion'''
        return self.rAxisMain, self.binStdV[ion['idx']], self.binStdVsig[ion['idx']]  # km/s

    def ionEffTemp(self, ion):
        '''Returns the Effective line temperatures of an input ion'''
        rAxis, velocities, yerr = self.ionEffVelocity(ion)

        # Convert the velocities to Temperatures
        temps = self.vel2T(ion, velocities)
        
        const = ion['mIon'] / (2 * self.env.KB) * 10 ** 10
        tError = [dx * 2 / x * tt / const / 10 ** 6 for dx, x, tt in zip(yerr, velocities, temps)]
        return rAxis, temps, tError

    def ionLineLabel(self, ion):
        """Return a nice label for the spectral line produced by an ion"""
        wav = int(np.round(ion['lam00'], 0))
        if wav == 1038: wav = 1037
        thisLab = '{} {}: {}'.format(ion['eString'].title(), self.write_roman(ion['ionNum']), wav)
        return thisLab

    def plotAsTemperature1(self, case=1, ax=None, label=True, ls='-', useIons=False, oneLegend=False, **kwargs):
        """Plot the temperature measurements vs height"""
        # Initialize the Plot
        fig, ax1, show = self.getAx(ax)

        firstLine = True
        ## Plot the Effective Temperature from Width Only for each ion
        for znum, ion in enumerate(self.ions):
            if useIons:
                if not znum in useIons: continue
            # Get the line widths
            rAxis, temps, tError = self.ionEffTemp(ion)
            zAxis = [rr - 1 for rr in rAxis]

            if True:  # Plot the Raw Temperatures
                if label is True:
                    thisLab = ion['lineString'] #self.ionLineLabel(ion)
                elif not label is False: thisLab = label
                else: thisLab = None
                if not firstLine and oneLegend: thisLab = None
                ax1.plot(zAxis, temps, color=ion['c'], zorder=znum, label=thisLab, ls=ls, **kwargs)

            if False:  # Plot the Modified Temperatures
                thisLab = "Line Temperature (Mod)"
                if not ion['ionNum'] == 13: thisLab = None

                modTemps = [tt / self.env.interp_w2_thermal(zz + 1) for tt, zz in zip(temps, zAxis)]
                ax1.plot(zAxis, modTemps, color=ion['c'], zorder=znum, label=thisLab, ls=':')

            if True:  # Plot the floorHeights
                zVal = ion['floorHeightZ']
                idx = self.env.find_nearest(zAxis, zVal)
                value = temps[idx]
                ax1.plot(zVal, value, '^', c=ion['c'], markeredgecolor='k', zorder=1000, markersize=8)
            firstLine=False

        ## Plot the POS Temperature from the Model
        rAxisGood = np.logspace(np.log10(np.min(rAxis)), np.log10(np.max(rAxis)), 3000)
        zAxisGood = [rr - 1 for rr in rAxisGood]

        expT = [self.env.interp_T(rx) / 10 ** 6 for rx in rAxisGood]
        gwExpT = [self.env.interp_w2_thermal(rx) * tt for rx, tt in zip(rAxisGood, expT)]

        ax1.plot(zAxisGood, expT, 'k:', label='POS Temp' if label and not oneLegend else None, zorder=znum + 10, lw=3)
        # ax1.plot(zAxisGood, gwExpT, 'm', label='Weighted POS Temp', zorder=znum + 3, lw=2)

        # #############Plot the slopes - the temperatures Moran Style
        if False:
            ax1.errorbar(zAxis, self.fitTemps, zorder=znum + 1, fmt='bo', yerr=self.fitTempErrors,
                         label='Fit Temperature', capsize=2, markersize=4)

            # Same thing but corrected with f3
            modFitTemps = [fT / self.env.interp_w2_thermal(rx) for rx, fT in zip(rAxis, self.fitTemps)]
            ax1.errorbar(zAxis, modFitTemps, zorder=znum + 3, fmt='ro', yerr=self.fitTempErrors,
                         label='Weighted Temperature', capsize=2, markersize=4)

        if case == 1:
            ax1.set_xlim((10 ** -2, 4))
        elif case == 2:
            ax1.set_xlim((10 ** -2, 10))
            ax1.set_ylim((0.1, 1000))
            ax1.set_yscale('log')

        if label and show: ax1.legend(frameon=False, ncol=2)
        ax1.set_xscale('log')
        ax1.set_ylabel('T (MK)')

        # ax1.set_ylim([0.95, 1.4])
        import matplotlib.ticker as tk
        formatter = tk.ScalarFormatter()
        formatter.set_scientific(False)
        # ax1.xaxis.set_major_formatter(formatter)
        # ax1.xaxis.set_minor_formatter(formatter)

        if show:
            ax1.set_title("Inferred Ion Temperatures")
            self.env.solarAxis(ax1, 2)
            fig.set_size_inches(5.5, 4.5)
            plt.tight_layout()
            plt.show()

    def plotAsTemperature2(self):
        """Plot the temperature measurements vs height"""

        # Initialize the Plot
        fig, ax1 = plt.subplots()

        ## Plot the Effective Temperature from Width Only for each ion
        for znum, ion in enumerate(self.ions):

            # Get the line widths
            rAxis, temps, tError= self.ionEffTemp(ion)
            zAxis = [rr - 1 for rr in rAxis]

            if False:  # Plot the Raw Temperatures
                thisLab = "Individual Ion Line Temperatures"
                # if not ion['ionNum'] == 13: thisLab = None
                wav = int(np.round(ion['lam00'], 0))
                if wav == 1038: wav = 1037
                thisLab = '{} {}: {}'.format(ion['eString'].title(), self.write_roman(ion['ionNum']), wav)
                ax1.plot(zAxis, temps, color=ion['c'], zorder=znum, label=thisLab, ls=ion['ls'])

            if False:  # Plot the Modified Temperatures
                thisLab = "Line Temperatures (Mod)"
                if not ion['cNum'] == 6: thisLab = None

                modTemps = [tt / self.env.interp_w2_thermal(zz + 1) for tt, zz in zip(temps, zAxis)]
                ax1.plot(zAxis, modTemps, color=ion['c'], zorder=znum, label=thisLab, ls=ion['ls'])

        ## Plot the POS Temperature from the Model
        rAxisGood = np.logspace(np.log10(np.min(rAxis)), np.log10(np.max(rAxis)), 3000)
        zAxisGood = [rr - 1 for rr in rAxisGood]

        expT = [self.env.interp_T(rx) / 10 ** 6 for rx in rAxisGood]
        gwExpT = [self.env.interp_w2_thermal(rx) * tt for rx, tt in zip(rAxisGood, expT)]

        ax1.plot(zAxisGood, expT, 'k:', label='POS Temperature', zorder=0, lw=2.5)
        # ax1.plot(zAxisGood, gwExpT, 'm', label='Weighted POS Temp', zorder=znum + 3, lw=2)

        # #############Plot the slopes - the temperatures Moran Style
        if True:
            ax1.errorbar(zAxis, self.fitTemps, zorder=znum + 1, fmt='bo', yerr=self.fitTempErrors,
                         label='Line-fit Temperature', capsize=2, markersize=4)

            # Same thing but corrected with f3
            modFitTemps = [fT / self.env.interp_w2_thermal(rx) for rx, fT in zip(rAxis, self.fitTemps)]
            ax1.errorbar(zAxis, modFitTemps, zorder=znum + 3, fmt='ro', yerr=self.fitTempErrors,
                         label='Corrected Temperature', capsize=2, markersize=4)
        # #NON THERMAL STUFF

        # expWind = [self.env.cm2km(self.env.interp_rx_dat_log(rx, self.env.ur_raw)) for rx in labels]
        # lns3 = ax2.plot(labels, expWind, 'c--', label = 'POS Model Wind Speed')

        # expWaves = [self.env.cm2km(self.env.interp_vrms(rx)) for rx in labels]
        # lns3 = ax2.plot(labels, expWaves, '--', label = 'POS Model Wave RMS', color = 'orange')

        ##expTot = [np.sqrt(x**2 + y**2) for x, y in zip(expWind, expWaves)]
        ##lns3 = ax2.plot(labels, expTot, '--', label = 'POS Model Total RMS', color = 'black')

        # oneLab1 = "Full"
        # oneLab2 = "Thermal"
        # oneLab3 = "GW Wind"
        # oneLab4 = "GW Waves"
        # oneLab5 = "GW Total Non-Thermal"
        # oneLab6 = "Thermal"
        ##Plot the intercepts - the VRMS
        # for ion in self.ions:
        #    self.makeVrms(ion)
        #    #lns4 = ax2.plot(self.rAxisMain, ion['expectedRms'], 'm:', label = oneLab1)
        #    #lns4 = ax2.plot(self.rAxisMain, ion['V_thermal'], 'c:', label = oneLab2)
        #    #_    = ax1.plot(self.rAxisMain, ion['V_thermal'], 'b:', label = oneLab6)
        #    #lns4 = ax2.plot(self.rAxisMain, ion['V_wind'], 'g:', label = oneLab3)
        #    #lns4 = ax2.plot(self.rAxisMain, ion['V_waves'], 'y:', label = oneLab4)
        #    lns4 = ax2.plot(self.rAxisMain, ion['V_nt'], 'k:', label = oneLab5)
        #    oneLab1 = None
        #    oneLab2 = None
        #    oneLab3 = None
        #    oneLab4 = None
        #    oneLab5 = None
        #    oneLab6 = None

        # lns2, _, _ = ax2.errorbar(labels, intercepts, fmt ='ro-', yerr = interceptErrors, label = 'Fit Non-Thermal Velocity', capsize = 4)
        # ax2.set_xlabel('Impact Parameter')
        # ax2.set_ylabel('km/s')
        # ax2.legend()

            ax1.legend(frameon=False)
            ax1.set_xscale('log')
            ax1.set_xlim((0.1, 4))
            ax1.set_ylim((1.0, 1.36))
            # ax1.set_ylim([0.95, 1.4])
            import matplotlib.ticker as tk
            formatter = tk.ScalarFormatter()
            formatter.set_scientific(False)
            # ax1.xaxis.set_major_formatter(formatter)

            self.env.solarAxis(ax1, 2)
            ax1.xaxis.set_minor_formatter(tk.NullFormatter())
            # ax1.set_xlabel('Observation Height Above Photosphere')
            ax1.set_ylabel('T (MK)')
            fig.set_size_inches(6,5.25)
            # plt.title("Results from Moran Fitting")

            plt.tight_layout()
            plt.show()

    def plotAsVelocity(self, ax=None, useIons=None, label=True, plotPos=1, **kwargs):
        """Plot the measurements as velocities"""
        self.reassignColors()
        # Create the plot and label it
        fig,ax,show=self.getAx(ax)

        if not plotPos is False:
            thisLab = "POS Wind at {}%".format(int(plotPos*100))
            posWind = [plotPos * self.env.interp_ur(rx) / 10 ** 5 for rx in self.rAxisMain]
            ax.plot(self.zAxisMain, posWind, 'k:', label=thisLab, lw=3, zorder=10)
            plotPos = False

        for ion in self.ions:
            if useIons:
                if not ion['cNum'] in useIons: continue
            rAxis, velocities, vError = self.ionEffVelocity(ion)
            zAxis = self.env.r2zAxis(rAxis)

            # ax.errorbar(zAxis, velocities, yerr=vError, label=self.ionLineLabel(ion), c=ion['c'])
            if label:
                thisLabel = label #ion['lineString'] #self.ionLineLabel(ion)
            else: thisLabel = None
            # if ion['cNum'] == 1:
            #     ls='--'
            #     thisLabel = None
            # else: ls ='-'

            ax.plot(zAxis, velocities, label=thisLabel, c=ion['c'], **kwargs)

        ax.set_yscale('log')
        ax.set_ylabel('Velocity (km/s)')
        ax.set_ylim((1,1000))
        ax.set_xlim((0.01,10))


        if show:
            plt.tight_layout()
            self.env.solarAxis(ax, 2)
            plt.show()

        if False:
            # Plot the histograms in the background
            # self.plotHistograms(ion, ax)

            # Do the chi-squared test
            # self.makeVrms(ion)
            # self.chiTest(ion)
            # # height = 0.9
            # # left = 0.65 + 0.09
            # # shift = 0.1
            # # plt.figtext(left + shift, height + 0.04, "Fit to the Mean")
            # # plt.figtext(left + shift, height + 0.02, "Chi2 = {:0.3f}".format(self.chi_mean))
            # # plt.figtext(left + shift, height, "Chi2_R = {:0.3f}".format(self.rChi_mean))

            if self.hahnPlot:
                # Plot the Hahn Measurements
                ax.errorbar(self.env.hahnAbs, self.env.hahnPoints, yerr=self.env.hahnError, fmt='gs',
                            label='Hahn Observations', capsize=4)
                ax.plot(self.rAxisMain, self.hahnV, label="HahnV", color='g')

            # Plot the expected values

            # ax.plot(self.rAxisMain, ion['expectedRms'], label='Expected', color='b')

            # Plot the results of the binned Test

            # locs, width, error = self.ionEffVelocity(ion)
            # ax.errorbar(locs, width, yerr=error, fmt='mo',
            #             label="Binned Profiles", capsize=6)

            # Plot Resolution Limit
            diff = np.diff(ion['lamAx'])[0]
            minrez = self.std2V(diff, ion)
            psfrez = self.std2V(ion['psfSig_e'], ion)

            # flr = np.ones_like(self.rAxisMain)*minrez
            ax.axhline(minrez, color='k', linewidth=2, label='Lam Rez')
            ax.axhline(psfrez, color='k', linewidth=2, linestyle=':', label='PSF Rez')
            # plt.plot(self.rAxisMain, flr, label = "Rez Limit", color = 'k', linewidth = 2)

            ##Put numbers on plot of widths
            # for xy in zip(histLabels, self.statV[2][0]):
            #    plt.annotate('(%.2f)' % float(xy[1]), xy=xy, textcoords='data')

            # Put numbers on plot of widths
            # locs, width, error = self.ionEffVelocity(ion)
            # for xy in zip(locs, width):
            #    ax.annotate('(%.2f)' % float(xy[1]), xy=xy, textcoords='data')

            if ion['idx'] == 0: ax.legend(loc=2)
            if ion['idx'] == len(self.ions) - 1: ax.set_xlabel(self.xlabel)
            plt.setp(ax.get_xticklabels(), visible=True)
            ax.set_ylabel('Km/s')
            ax.set_xlabel('Impact Parameter')
            spread = 0.2
            ax.set_xlim([self.rAxisMain[0] - spread, self.rAxisMain[-1] + spread])  # Get away from the edges
            ax.set_ylim([0, self.histMax])

            # if self.plotRatio: self.ratioPlot()

            plt.legend()

            # grid.maximizePlot()

            # filePath = os.path.join('../fig/2018/widths/',self.batchName)
            filePath = '../fig/widths/'

            if self.pWidth == 'save':
                plt.savefig(filePath + '{}_{}_{}.png'.format(ion['ionString'], ion['ionNum'], ion['lam00']))
                plt.close(fig)
            else:
                plt.show(False)

            return

    def plotMultiWidth(self):
        """Plot the widthplot for every ion"""
        print('Plotting Widthplots...', end='')
        for ion in self.ions:
            self.plotWidth(ion)
        print('Done')
        return

    def plotLabel(self):
        # Display the run flags
        height = 0.9
        left = 0.09
        shift = 0.1
        try:
            self.intTime
        except:
            self.intTime = np.nan
        plt.figtext(left + 0.18, height + 0.08, "Lines/Impact: {}".format(self.Npt))
        plt.figtext(left + 0.36, height + 0.08, "Seconds: {} ({})".format(self.intTime, self.timeAx[-1]))
        plt.figtext(left + 0.60, height + 0.08, "Batch: {}".format(self.batchName))
        plt.figtext(left, height + 0.08, "Wind: {}".format(self.copyPoint.windWasOn))
        plt.figtext(left, height + 0.04, "Waves: {}".format(self.copyPoint.waveWasOn))
        plt.figtext(left, height + 0.00, "B: {}".format(self.copyPoint.bWasOn))

    def plotHistograms(self, ion, ax):
        # Plot the actual distribution of line widths in the background
        histLabels = []
        edges = []
        hists = []
        low = []
        self.medians = []
        high = []

        small = 1e16
        big = 0
        for stdlist in self.allStd[ion['idx']]:
            newBig = np.abs(np.ceil(np.amax(stdlist)))
            newSmall = np.abs(np.floor(np.amin(stdlist)))

            small = int(min(small, newSmall))
            big = int(max(big, newBig))
        throw = int(np.abs(np.ceil(big - small))) / 5
        throw = np.arange(0, self.histMax, 5)
        spread = 2
        vmax = 0
        for stdlist, label in zip(self.allStd[ion['idx']], self.rAxisMain):
            hist, edge = np.histogram(stdlist, throw)  # , range = [small-spread,big+spread])
            hist = hist / np.sum(hist)
            vmax = max(vmax, np.amax(hist))
            histLabels.append(label)
            edges.append(edge)
            hists.append(hist)

            quarts = np.percentile(stdlist, self.qcuts)
            low.append(quarts[0])
            self.medians.append(quarts[1])
            high.append(quarts[2])

        array = np.asarray(hists).T
        diff = np.average(np.diff(np.asarray(histLabels)))
        histLabels.append(histLabels[-1] + diff)
        ed = edges[0][:-1]
        xx, yy = np.meshgrid(histLabels - diff / 2, ed)
        histLabels.pop()

        if self.plotBkHist:
            hhist = ax.pcolormesh(xx, yy, array, cmap='YlOrRd', label="Sim Hist")
            hhist.cmap.set_under("#FFFFFF")
            hhist.set_clim(1e-8, vmax)
            # cbar = plt.colorbar()
            # cbar.set_label('Number of Lines')

        # Plot the confidence intervals
        ax.plot(histLabels, low, 'c:', label="{}%".format(self.qcuts[0]), drawstyle="steps-mid")
        ax.plot(histLabels, self.medians, 'c--', label="{}%".format(self.qcuts[1]), drawstyle="steps-mid")
        ax.plot(histLabels, high, 'c:', label="{}%".format(self.qcuts[2]), drawstyle="steps-mid")

        # Plot the Statistics from the Lines
        self.lineWidths = self.statV[ion['idx']][2][0]
        self.lineWidthErrors = self.statV[ion['idx']][2][1]
        ax.errorbar(histLabels, self.lineWidths, yerr=self.lineWidthErrors, fmt='bo', label='Simulation', capsize=4)
        self.histlabels = histLabels

    def plotWidth(self, ion):
        """Generate the primary plot"""

        # Create the plot and label it
        fig, ax = plt.subplots(figsize=(12, 8))

        self.plotLabel()

        str1 = "{}: {}\nEnvs: {}; Lines per Env: {}; Lines per Impact: {}\n".format(self.batchName, self.completeTime,
                                                                                    self.Nenv, self.Nrot, self.Npt)
        str2 = "usePsf: {}                                          reconType: {}".format(self.usePsf, self.reconType)
        fig.suptitle(str1 + str2)

        ionStr = '{}_{} : {} -> {}, $\lambda_0$: {} $\AA$'.format(ion['ionString'], ion['ionNum'], ion['upper'],
                                                                  ion['lower'], ion['lam00'])
        ax.set_title(ionStr)

        labels = self.getLabels()

        # Plot the histograms in the background
        self.plotHistograms(ion, ax)

        # Do the chi-squared test
        self.makeVrms(ion)
        self.chiTest(ion)
        # height = 0.9
        # left = 0.65 + 0.09
        # shift = 0.1
        # plt.figtext(left + shift, height + 0.04, "Fit to the Mean")
        # plt.figtext(left + shift, height + 0.02, "Chi2 = {:0.3f}".format(self.chi_mean))
        # plt.figtext(left + shift, height, "Chi2_R = {:0.3f}".format(self.rChi_mean))

        if self.hahnPlot:
            # Plot the Hahn Measurements
            ax.errorbar(self.env.hahnAbs, self.env.hahnPoints, yerr=self.env.hahnError, fmt='gs',
                        label='Hahn Observations', capsize=4)
            ax.plot(self.rAxisMain, self.hahnV, label="HahnV", color='g')

            # Plot the expected values

        ax.plot(self.rAxisMain, ion['expectedRms'], label='Expected', color='b')

        # Plot the results of the binned Test

        locs, width, error = self.ionEffVelocity(ion)
        ax.errorbar(locs, width, yerr=error, fmt='mo',
                    label="Binned Profiles", capsize=6)

        # Plot Resolution Limit
        diff = ion['lamAx'][1] - ion['lamAx'][0]
        minrez = self.std2V(diff, ion)
        psfrez = self.std2V(ion['psfSig_e'], ion)

        # flr = np.ones_like(self.rAxisMain)*minrez
        ax.axhline(minrez, color='k', linewidth=2, label='Lam Rez')
        ax.axhline(psfrez, color='k', linewidth=2, linestyle=':', label='PSF Rez')
        # plt.plot(self.rAxisMain, flr, label = "Rez Limit", color = 'k', linewidth = 2)

        ##Put numbers on plot of widths
        # for xy in zip(histLabels, self.statV[2][0]):
        #    plt.annotate('(%.2f)' % float(xy[1]), xy=xy, textcoords='data')

        # Put numbers on plot of widths
        # locs, width, error = self.ionEffVelocity(ion)
        # for xy in zip(locs, width):
        #    ax.annotate('(%.2f)' % float(xy[1]), xy=xy, textcoords='data')

        if ion['idx'] == 0: ax.legend(loc=2)
        if ion['idx'] == len(self.ions) - 1: ax.set_xlabel(self.xlabel)
        plt.setp(ax.get_xticklabels(), visible=True)
        ax.set_ylabel('Km/s')
        ax.set_xlabel('Impact Parameter')
        spread = 0.2
        ax.set_xlim([self.rAxisMain[0] - spread, self.rAxisMain[-1] + spread])  # Get away from the edges
        ax.set_ylim([0, self.histMax])

        # if self.plotRatio: self.ratioPlot()

        plt.legend()

        # grid.maximizePlot()

        # filePath = os.path.join('../fig/2018/widths/',self.batchName)
        filePath = '../fig/widths/'

        if self.pWidth == 'save':
            plt.savefig(filePath + '{}_{}_{}.png'.format(ion['ionString'], ion['ionNum'], ion['lam00']))
            plt.close(fig)
        else:
            plt.show(False)

        return

    def ratioPlot(self):
        # Plots the ratio between the raw fits and the reconstructed fits.
        plt.figure()
        histlabels = []
        edges = []
        hists = []

        low = []
        medians = []
        high = []

        small = 1e16
        big = 0
        for ratioList in self.allRatio:
            newBig = np.abs(np.ceil(np.amax(ratioList)))
            newSmall = np.abs(np.floor(np.amin(ratioList)))

            small = int(min(small, newSmall))
            big = int(max(big, newBig))
        throw = int(np.abs(np.ceil(big - small)))

        for ratioList, label in zip(self.allRatio, self.rAxisMain):
            hist, edge = np.histogram(ratioList, 200, range=[small, big])
            # hist = hist / np.amax(hist)
            histlabels.append(label)
            edges.append(edge)
            hists.append(hist)

            quarts = np.percentile(ratioList, self.qcuts)
            low.append(quarts[0])
            medians.append(quarts[1])
            high.append(quarts[2])

        array = np.asarray(hists).T
        diff = np.average(np.diff(np.asarray(histlabels)))
        histlabels.append(histlabels[-1] + diff)
        ed = edges[0][:-1]
        xx, yy = np.meshgrid(histlabels - diff / 2, ed)
        histlabels.pop()

        hhist = plt.pcolormesh(xx, yy, array, cmap='YlOrRd', label="Ratio Hist")
        hhist.cmap.set_under("#FFFFFF")
        hhist.set_clim(1e-8, np.amax(array))
        cbar = plt.colorbar()
        cbar.set_label('Number of Occurances')

        # Plot the Line Ratios
        plt.errorbar(histlabels, self.statV[5][0], yerr=self.statV[5][1], fmt='co', label='Mean/Std', capsize=4)

        plt.axhline(1, color='k')
        plt.plot(self.histlabels, low, 'c:', label="{}%".format(self.qcuts[0]), drawstyle="steps-mid")
        plt.plot(self.histlabels, medians, 'c--', label="{}%".format(self.qcuts[1]), drawstyle="steps-mid")
        plt.plot(self.histlabels, high, 'c:', label="{}%".format(self.qcuts[2]), drawstyle="steps-mid")

        # Display the run flags
        height = 0.9
        left = 0.09
        shift = 0.1

        plt.figtext(left, height + 0.04, "Wind: {}".format(self.copyPoint.windWasOn))
        plt.figtext(left, height + 0.02, "Waves: {}".format(self.copyPoint.waveWasOn))
        plt.figtext(left, height, "B: {}".format(self.copyPoint.bWasOn))

        str1 = "{}: {}\nEnvs: {}; Lines per Env: {}; Lines per Impact: {}\n".format(self.batchName, self.completeTime,
                                                                                    self.Nenv, self.Nrot, self.Npt)
        str2 = "usePsf: {}                                          reconType: {}".format(self.usePsf, self.reconType)
        plt.suptitle(str1 + str2)

        plt.title("Sigma_Reconstructed / Sigma_Raw_Fit")
        plt.ylabel('Ratio')
        plt.xlabel('Impact Parameter')
        plt.legend()
        plt.show()




# For doing a multisim at many impact parameters


class impactsim(batchjob):
    def __init__(self, batchName, env, impacts, iter=1, N='auto',
                 rez=None, size=None, timeAx=[0], printSim=False, printOut=True, printMulti=True, printQuiet=False,
                 qcuts=[16, 50, 84], allSave=False):
        comm = MPI.COMM_WORLD
        self.size = comm.Get_size()
        self.rank = comm.Get_rank()
        self.root = self.rank == 0
        self.allSave = allSave
        self.count = 0
        self.Nb = len(impacts)
        self.batchName = batchName
        self.timeAx = timeAx
        self.qcuts = qcuts
        self.env = env
        self.N = N
        self.rez = rez
        self.viewSize = size
        self.iter = iter
        self.impacts = impacts
        self.print = printOut
        self.printMulti = printMulti
        self.printSim = printSim
        self.printQuiet = printQuiet
        self.xlabel = 'Impact Parameter'

        if printQuiet:
            self.print = False
            self.printMulti = False
            self.printSim = False

        self.defineLines()

        super().__init__()

        return

    def hahnFit(self, r, r0=1.05, vth=25.8, vnt=32.2, H=0.0657):
        veff = np.sqrt(vth ** 2 + vnt ** 2 * np.exp(-(r - r0) / (r * r0 * H)) ** (-1 / 2))
        return veff

    def defineLines(self):
        """Define which lines will be simulated"""
        # Lines per environment
        print(self.size)
        self.Nslaves = max(self.size - 1, 1)
        maxLines = self.Nslaves * self.iter
        self.Nenv = min(self.env.nBmap, self.env.maxEnvs, maxLines)
        self.env.Nenv = self.Nenv
        lines_env = np.floor(maxLines / self.Nenv)
        self.Nrot = int(max(lines_env, 1))
        self.env.Nrot = self.Nrot

        # Lines per impact
        self.Npt = self.Nrot * self.Nenv

        # Total Lines
        self.Ntot = self.Npt * self.Nb

        MPI.COMM_WORLD.barrier()

        self.fullBatch = []

        for b in self.impacts:
            # Determine length in x
            x0 = 100 * b

            # Create Batch
            gridPack = []
            for envInd in np.arange(self.Nenv):
                thisSet = grid.rotLines(N=self.Nrot, b=b, rez=self.rez, size=self.viewSize, x0=x0, findT=False, envInd=envInd)
                gridPack.extend(thisSet)

            self.fullBatch.append(gridPack)

        # pointsEach = len(self.fullBatch[0])

        # print(f"Points/Impact: {pointsEach}")
        # print(f"Points/Impact: {self.Npt}")
        # print(f"Points/Env: {self.Nrot}")

class timesim(batchjob):
    def __init__(self, batchName, envs, Nb=10, iter=1, b0=1.05, b1=1.50, N=(1500, 10000),
                 rez=None, size=None, timeAx=[0], length=10, printSim=False, printOut=True, printMulti=True,
                 qcuts=[16, 50, 84], spacing='lin'):
        comm = MPI.COMM_WORLD
        self.size = comm.Get_size()
        self.root = comm.Get_rank() == 0
        self.count = 0
        self.Nb = Nb
        self.batchName = batchName
        self.timeAx = timeAx
        self.qcuts = qcuts
        try:
            self.Nenv = len(envs)
        except:
            self.Nenv = 1

        # Lines per environment
        if self.root and self.size < self.Nenv:
            print('**Warning: More envs than PEs, will take additional time**')
        self.Nrot = np.floor(iter * max(1, self.size / self.Nenv))

        # Lines per impact
        self.Npt = self.Nrot * self.Nenv
        # print("{} lines per run".format(self.Npt))
        # Total Lines
        self.Ntot = self.Npt * self.Nb

        self.print = printOut
        self.printMulti = printMulti
        self.printSim = printSim

        self.N = N

        # base = 200

        ##if b1 is not None:
        # if b1 is not None:
        #    if spacing.casefold() in 'log'.casefold():
        #        steps = np.linspace(b0,b1,Nb)
        #        logsteps = base**steps
        #        logsteps = logsteps - np.amin(logsteps)
        #        logsteps = logsteps / np.amax(logsteps) * (b1-b0) + b0
        #        self.labels = logsteps

        #        #self.labels = np.round(np.logspace(np.log(b0)/np.log(base),np.log(b1)/np.log(base), Nb, base = base), 4)
        #    else: self.labels = np.round(np.linspace(b0,b1,Nb), 4)
        # else: self.labels = np.round([b0], 4)

        self.impacts = self.labels
        self.xlabel = 'Impact Parameter'
        self.fullBatch = []
        for ind in self.impacts:
            self.fullBatch.append(grid.rotLines(N=self.Nrot, b=ind, rez=rez, size=size, x0=length, findT=False))

        super().__init__(envs)

        return


class imagesim(batchjob):
    def __init__(self, batchName, env, NN=[5, 5], rez=[0.5, 0.5], target=[0, 1.5], len=10):
        """Set variables and call the simulator"""
        comm = MPI.COMM_WORLD
        self.size = comm.Get_size()
        self.root = comm.Get_rank() == 0
        self.plotbinFitsNow = False
        try:
            self.env = env[0]
        except:
            self.env = env
        # print(self.env)
        self.print = True
        self.printMulti = True
        self.printSim = False
        self.batchName = batchName
        self.labels = np.round([1], 4)
        self.Nb = 1
        # self.N = (200,600)
        self.NN = NN
        self.timeAx = self.timeAx3D  # [0]

        self.impacts = self.labels
        self.xlabel = 'Nothing'
        self.fullBatch, (self.yax, self.zax) = grid.image(N=NN, rez=rez, target=target, len=len)
        # multisim.destroySims = True

        super().__init__(self.env)

        if self.root: self.imageStats()

        return

    def imageStats(self):
        """Do all the post processing on the lines"""
        print("Finding Line Stats...")
        bar = pb.ProgressBar(len(self.profiless[0]))
        self.makePSF()

        centroids = []
        sigmas = []
        for profile in self.profiless[0]:
            # Find the centroids and the sigmas
            for ion, prof in zip(self.ions, profile):
                # import pdb
                # pdb.set_trace()
                Stats = self.findProfileStats(prof, ion)
                centroids.append(Stats[1] - ion['lam00'])
                sigmas.append(Stats[2])
            bar.increment()
            bar.display()
        bar.display(True)

        self.centroidss = [centroids]
        self.sigmass = [sigmas]

        # Store all the variables and save
        self.reconstructAll()
        self.save(printout=True)

    def reconstructAll(self):
        """Get out the arrays after they were jumbled from the compute process"""
        self.intensity = self.reconstruct(self.intensitiess)
        self.pB = self.reconstruct(self.pBss)
        self.centroid = self.reconstruct(self.centroidss)
        self.sigma = self.reconstruct(self.sigmass)

    def reconstruct(self, array):
        """Re-order an array to account for random parallel order"""
        indices = [x[2] for x in self.indicess[0]]
        data = array[0]
        out = np.zeros_like(data)
        for ind, dat in zip(indices, data):
            out[ind] = dat
        return out.reshape(self.NN)

    def plot(self):
        # self.indices = [np.array([x[2] for x in self.indicess[0]])]
        # plt.imshow(self.reconstruct(self.indices))
        # plt.show()

        # profiles = self.profiless[0]
        # i = 0
        # for profile in profiles:
        #    plt.plot(profile)
        #    i += 1
        #    #if i > 1000: continue
        # plt.show()

        # int = self.intensitiess[0]
        # hist, edge = np.histogram(int, bins = 100, range = (np.nanmin(int), np.nanmax(int)) )
        # plt.plot(edge[:-1], hist)
        # plt.show()

        # plt.imshow(np.log10(np.array(self.intensitiess[0]).reshape(self.NN)))
        # plt.show()
        # self.reconstructAll()
        # self.save()
        print(self.NN)

        invert = True

        plotInt = True
        plotpB = False
        plotStats = False

        ystring = 'Solar Y ($R_\odot$)'
        zstring = 'Solar Z ($R_\odot$)'
        # self.yax = self.axis[0]
        # self.zax = self.axis[1]
        try:
            self.centroid
        except:
            self.imageStats()

        # Process the variables
        centroid = self.centroid
        sigma = self.sigma

        intensityRaw = self.intensity
        intensityCor = self.coronagraph(intensityRaw)
        intensityLog = np.log10(intensityRaw)

        pBRaw = self.pB
        pBCor = self.coronagraph(pBRaw)
        pBLog = np.log10(pBRaw)

        if invert:
            # Invert if Desired
            self.zax, self.yax = self.yax, self.zax
            ystring, zstring = zstring, ystring
            pBRaw, pBCor, pBLog = pBRaw.T, pBCor.T, pBLog.T
            intensityRaw, intensityCor, intensityLog = intensityRaw.T, intensityCor.T, intensityLog.T
            centroid = centroid.T
            sigma = sigma.T

        # Plot

        if plotInt:
            fig0, (ax0, ax1) = plt.subplots(1, 2, True, True)
            fig0.set_size_inches(12, 9)
            fig0.suptitle(self.batchName)
            intensityLog = np.ma.masked_invalid(intensityLog)
            intensityCor = np.ma.masked_invalid(intensityCor)
            # pdb.set_trace()
            p0 = ax0.pcolormesh(self.zax, self.yax, intensityCor, vmin=0, vmax=1)
            ax0.patch.set(hatch='x', edgecolor='black')
            ax0.set_title(
                'Total Intensity - Coronagraph')  # \nMIN:{!s:.2} MAX:{!s:.2}'.format(np.nanmin(intensityCor),np.nanmax(intensityCor)))
            ax0.set_ylabel(ystring)
            ax0.set_xlabel(zstring)
            plt.colorbar(p0, ax=ax0)

            p1 = ax1.pcolormesh(self.zax, self.yax, intensityLog, vmin=np.nanmin(intensityLog),
                                vmax=np.nanmax(intensityLog) * 0.9)
            ax1.set_title('Total Intensity - Log')
            ax1.patch.set(hatch='x', edgecolor='black')
            ax1.set_xlabel(zstring)
            plt.colorbar(p1, ax=ax1)
            plt.tight_layout()

        if plotpB:
            fig2, (ax4, ax5) = plt.subplots(1, 2, True, True)
            fig2.suptitle(self.batchName)
            pBLog = np.ma.masked_invalid(pBLog)
            pBCor = np.ma.masked_invalid(pBCor)

            p0 = ax4.pcolormesh(self.zax, self.yax, pBCor, vmin=0, vmax=1)
            ax4.patch.set(hatch='x', edgecolor='black')
            ax4.set_title('Polarization Brightness - Coronagraph\nMIN:{!s:.2} MAX:{!s:.2}'.format(np.nanmin(pBCor),
                                                                                                  np.nanmax(pBCor)))

            ax5.pcolormesh(self.zax, self.yax, pBLog, vmin=np.nanmin(pBLog), vmax=6)
            ax5.set_title('Polarization Brightness - Log')
            ax5.patch.set(hatch='x', edgecolor='black')
            plt.tight_layout()

        if plotStats:
            fig1, (ax2, ax3) = plt.subplots(1, 2, True, True)
            fig1.suptitle(self.batchName, verticalalignment='bottom')
            # import pdb
            # pdb.set_trace()
            fig1.set_size_inches(12, 9)
            centroid = np.multiply(centroid, 3e5 / self.env.lam0)
            sigma = self.std2V(sigma)

            centroid = np.ma.masked_invalid(centroid)
            throw = max(np.abs(np.nanmin(centroid)), np.abs(np.nanmax(centroid)))
            p2 = ax2.pcolormesh(self.zax, self.yax, centroid, cmap='RdBu', vmin=-throw, vmax=throw)
            ax2.patch.set(hatch='x', edgecolor='black')

            ax2.set_title('Centroid')
            ax2.set_ylabel(ystring)
            ax2.set_xlabel(zstring)
            cax1 = plt.colorbar(p2, ax=ax2)
            cax1.ax.set_title('km/s')

            sigma = np.ma.masked_invalid(sigma)
            p3 = ax3.pcolormesh(self.zax, self.yax, sigma, vmin=25,
                                vmax=200)  # , vmin = np.nanmin(sigma), vmax = np.nanmax(sigma)*0.8)
            ax3.patch.set(hatch='x', edgecolor='black')
            ax3.set_title('Line Width')
            ax3.set_xlabel(zstring)
            cax2 = plt.colorbar(p3, ax=ax3)
            cax2.ax.set_title('km/s')

            plt.tight_layout()

        plt.show()

        return
        # plt.colorbar(p0,cax=ax0)

    def coronagraph(self, array):
        """Normalize each radius so that there is better contrast"""
        # Set up impact bins
        zaxis = self.zax.tolist()
        yaxis = self.yax.tolist()
        mask = np.zeros_like(array, dtype=int)
        # self.rez = 50
        self.graphEdges = np.linspace(0.7 * np.amin(zaxis), 1.2 * np.amax(zaxis), self.corRez)
        # self.graphBins = np.zeros_like(self.graphEdges)
        self.graphList = [[] for x in np.arange(self.corRez)]
        self.graphList[0].append(0)

        yit = np.arange(len(yaxis))
        zit = np.arange(len(zaxis))

        # place each pixel intensity into an impact bin, and assign each pixel an impact
        for yy, yi in zip(yaxis, yit):
            for zz, zi in zip(zaxis, zit):
                r = np.sqrt(yy * yy + zz * zz)
                index = np.searchsorted(self.graphEdges, r)
                mask[yi, zi] = int(index)

                inten = array[yi, zi]
                self.graphList[index].append(inten)
                # self.graphBins[index] += inten

        # Get the statistics for each impact bin
        mins = []
        mids = []
        maxs = []
        ##TODO smooth these guys out
        for intensities in self.graphList:
            try:
                min = (np.nanmin(intensities))
                mid = (np.average(intensities))
                max = (np.nanmax(intensities))
            except:
                min, mid, max = np.nan, np.nan, np.nan
            mins.append(min)
            mids.append(mid)
            maxs.append(max)

            smins = ndimage.filters.gaussian_filter1d(mins, self.filt)
            smids = ndimage.filters.gaussian_filter1d(mids, self.filt)
            smaxs = ndimage.filters.gaussian_filter1d(maxs, self.filt)
            smins = ndimage.filters.gaussian_filter1d(smins, self.filt)
            smids = ndimage.filters.gaussian_filter1d(smids, self.filt)
            smaxs = ndimage.filters.gaussian_filter1d(smaxs, self.filt)

        # plt.plot(self.graphEdges,mins, 'b:')
        # plt.plot(self.graphEdges,mids, 'g:')
        # plt.plot(self.graphEdges,maxs, 'r:')

        # plt.plot(self.graphEdges,smins, 'b')
        # plt.plot(self.graphEdges,smids, 'g')
        # plt.plot(self.graphEdges,smaxs, 'r')

        # plt.show()

        if self.smooth:
            usemin = smins
            usemax = smaxs
        else:
            usemin = mins
            usemax = maxs

        # Create new scaled output array
        output = np.zeros_like(array)
        for yi in yit:
            for zi in zit:
                intensity = array[yi, zi]
                logint = (intensity)

                index = int(mask[yi, zi])
                inte = (logint - usemin[index]) / (usemax[index] - usemin[index])
                output[yi, zi] = inte
        # output[np.isnan(output)] = 0

        # plt.imshow(mask)
        # plt.show()

        return output

        # plt.pcolormesh(output)
        # plt.colorbar()
        # plt.show()

        # pdb.set_trace()
        # plt.plot(self.graphEdges, self.graphBins)
        # plt.show()
        # plt.pcolormesh(zaxis,yaxis,mask)
        # plt.show()


def pbRefinement(envsName, params, MIN, MAX, tol):
    # This function compares the pB at a height of zz with and without B, and finds the Bmin which minimizes the difference
    def runAtBminFull(params, Bmin):
        # This runs a multisim at a particular Bmin and returns the pB
        comm = MPI.COMM_WORLD
        root = comm.Get_rank() == 0
        simpoint.useB = True
        simpoint.g_Bmin = Bmin

        bat = impactsim(*params)
        if root:
            pBnew = bat.pBavg
            print("B = {}, pB = {}".format(Bmin, pBnew))
            sys.stdout.flush()
        else:
            pBnew = np.empty(1)
        comm.Bcast(pBnew, root=0)
        return pBnew

    def bisection(a, b, tol, f, pBgoal):
        # Given a function f, a tolerance, and a goal, this returns the value that solves for the goal.
        comm = MPI.COMM_WORLD
        root = comm.Get_rank() == 0
        Nmax = 20
        N = 0
        c = (a + b) / 2.0
        fc = f(c) - pBgoal
        flist = {}
        flist[c] = fc

        while np.abs(fc) > tol:
            N += 1
            if N > Nmax:
                if root: print("I failed to converge")
                break

            try:
                fc = flist[c]
            except:
                fc = f(c) - pBgoal
                flist[c] = fc
            try:
                fa = flist[a]
            except:
                fa = f(a) - pBgoal
                flist[a] = fa

            if fc == 0:
                return c
            elif fa * fc < 0:
                b = c
            else:
                a = c
            c = (a + b) / 2.0
        if root:
            print("Converged to {}, with pB = {}, in {} iterations".format(c, fc + pBgoal, N))
            print("The goal was {}".format(pBgoal))
        return c

    comm = MPI.COMM_WORLD
    root = comm.Get_rank() == 0
    if root:
        print("Beginning Refinement...")
        sys.stdout.flush()

    zz = params[4]
    len = params[10]
    rez = params[7]
    refenv = params[1][0]
    refgrd = grid.sightline([-len, 1e-8, zz], [len, 1e-8, zz], findT=True)

    from functools import partial
    runAtBmin = partial(runAtBminFull, params)

    # Get the reference line pB
    simpoint.useB = False
    lineSim = simulate(refgrd, refenv, N=rez, findT=True, getProf=True)
    pBgoal = lineSim.pB
    if root:
        print("The goal is pB = {}".format(pBgoal))
        sys.stdout.flush()

    # Converge to that line
    return bisection(MIN, MAX, tol, runAtBmin, pBgoal)

    # def runAtImpact(params, b):
    #    #This runs a multisim at a particular Bmin and returns the pB
    #    comm = MPI.COMM_WORLD
    #    root = comm.Get_rank() == 0
    #    params = ["fCalcs", envs, impactPoints, iterations, b, None, N_line, rez, size, timeAx, length, False, False, False]
    #    bat = impactsim(batchName, envs, impactPoints, iterations, b0, b1, N_line, rez, size, timeAx, length, printSim)
    #    if root:
    #        pBnew = bat.pBavg
    #        print("B = {}, pB = {}".format(Bmin, pBnew))
    #        sys.stdout.flush()
    #    else:
    #        pBnew = np.empty(1)
    #    comm.Bcast(pBnew, root=0)
    #    return pBnew


# def plotpB(maxN = 100):
#        path = os.path.normpath("../dat/pB/*.txt")
#        files = glob.glob(path)

#        ind = 0
#        for file in files:
#            if ind < maxN:
#                x = np.loadtxt(file)
#                absiss = x[:,0]
#                pBavg = x[:,1]
#                pBstd = x[:,2]
#                label = file.rsplit(os.path.sep, 1)[-1]
#                plt.plot(absiss, pBavg, '-o', label = label)#, yerr = pBstd)
#            ind += 1

#        plt.legend()
#        plt.yscale('log')
#        plt.ylabel('pB')
#        plt.xlabel('Impact Parameter')
#        plt.show()


# def doPB(self, filename):
#    if filename is not None:
#        self.pBavg = []
#        self.pBstd = []
#        path = os.path.normpath("../dat/pB/" + filename + ".txt")
#        with open(path, 'w') as f:
#            for label, pBs in zip(self.getLabels(),self.pBs):
#                data = np.asarray(pBs)
#                avg = np.average(data)
#                std = np.std(data)

#                self.pBavg.append(avg)
#                self.pBstd.append(std)

#                f.write("{}    {}    {}\n".format(label, avg, std))
#                f.flush()

# plt.errorbar(self.getLabels(), pBavg, yerr = pBstd, fmt = 'o')
# plt.yscale('log')
##plt.semilogy(self.getLabels(), pB)
# plt.show()


# From profileStats
# return [power, mu, sigout, skew, kurt, perr, ratio]


# error1 = np.sqrt(profNorm) + 1e-16 #, sigma = error2)
# error2 = np.sqrt(profileRaw) + 1e-16 #, sigma=error1)
# powerCon = poptCon[0] * np.sqrt(np.pi * 2 * poptCon[2]**2)
##Output only the asked for type.
# if self.statType.casefold() in 'moment'.casefold():
#    power, mu, sigmaStatFix, skew, kurt, amp, sigmaStat = powerM, muM, sigmaMFix, skewM, kurtM, ampM, sigmaM
# elif self.statType.casefold() in 'gaussian'.casefold():
#    power, mu, sigmaStatFix, skew, kurt, amp, sigmaStat = powerG, muG, sigmaGFix, skewM, kurtM, ampCon, sigmaG
# else: raise Exception('Statistic Type Undefined')
# * 1.030086 #This is the factor that makes it the same before and after psf

# From makePSF
# import warnings
# with warnings.catch_warnings():
#    warnings.simplefilter("ignore")
#    import astropy.convolution as con
#    self.con = con
# if angSig is not None:
#    diff = np.abs(self.lamAx[1] - self.lamAx[0])
#    pix = int(np.ceil(angSig/diff))
#    self.psf = self.con.Gaussian1DKernel(pix)
#    #plt.plot(self.psf)
#    #plt.show()
# else: self.psf = None


def nothing():
    pass
