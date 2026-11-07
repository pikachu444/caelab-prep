1. Overview
This is a documentation for the code of Quality.
2. Compiling instructions
2.1. Tools
CMake, Visual Studio (2008, 2013, 2015, 2017)
2.2. Explanation of the folder
src: source files
CMakeList.txt and cmake are used in CMake for compiling
cpp contains source codes
2.3. External libraries
Eigen:  http://eigen.tuxfamily.org/index.php?title=Main_Page
Download the package, unzip it and put it somewhere and record the path (PATH_EIGEN).
In src/cmake/ FindEigen3.cmake, add PATH_EIGEN in the PATHS of find_path.
2.4. Compiling
Open CMake and set “source code” and “binaries” to be src and build, respectively. 
Choose default compiler and then click “Configure”. Usually it would fail the first time. Ignore it and click “Configure” again and it will be all right (because some intermediate files are needed).
Next click “Generate” and a VS project will be generated in the build folder.
Go to build folder, open ProjectName.sln and you will find three projects in this solution in VS. Right click the project with ProjectName and “Set as Startup Project”.
3. Executing instructions
Make sure Release mode is on rather than Debug in VS because it is much faster. 
How the program works and I/O, you can check the following article.
Y. Yu, X. Wei, A. Li, J. G. Liu, J. He and Y. J. Zhang: HexGen and Hex2Spline: Polycube-based Hexahedral Mesh Generation and Spline Modeling for Isogeometric Analysis Applications in LS-DYNA. Submitted to Springer INdAM Series, 2020.
All vtk files can be visualized in Paraview and All k files can be visualized in LS-Prepost.
