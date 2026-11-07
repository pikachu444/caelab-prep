// Round4 exact CAD queries. Existing solids only; no healing or Boolean edits.
#include <BRep_Builder.hxx>
#include <BRepTools.hxx>
#include <BRepClass3d_SolidClassifier.hxx>
#include <BRepBndLib.hxx>
#include <BRepGProp.hxx>
#include <GProp_GProps.hxx>
#include <Bnd_Box.hxx>
#include <STEPControl_Reader.hxx>
#include <Interface_Static.hxx>
#include <TopExp_Explorer.hxx>
#include <TopoDS_Shape.hxx>
#include <gp_Pnt.hxx>
#include <Standard_Failure.hxx>
#include <algorithm>
#include <chrono>
#include <cctype>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

int main(int argc, char** argv) {
  if (argc < 2) { std::cerr << "Usage: cad_query CAD_FILE [tolerance|--stats]\n"; return 2; }
  try {
    auto started = std::chrono::steady_clock::now();
    std::string name(argv[1]), suffix = name.substr(name.find_last_of('.') + 1);
    std::transform(suffix.begin(), suffix.end(), suffix.begin(), [](unsigned char c){return std::tolower(c);});
    TopoDS_Shape shape;
    // Reader diagnostics belong on stderr, not in the point-state protocol.
    auto original_stdout = std::cout.rdbuf(std::cerr.rdbuf());
    if (suffix == "brep") {
      BRep_Builder builder;
      if (!BRepTools::Read(shape, name.c_str(), builder)) throw std::runtime_error("BREP read failed");
    } else if (suffix == "step" || suffix == "stp") {
      Interface_Static::SetCVal("xstep.cascade.unit", "MM");
      STEPControl_Reader reader;
      if (reader.ReadFile(name.c_str()) != IFSelect_RetDone) throw std::runtime_error("STEP read failed");
      reader.TransferRoots();
      shape = reader.OneShape();
    } else throw std::runtime_error("Unsupported input suffix");
    std::cout.rdbuf(original_stdout);
    if (shape.IsNull()) throw std::runtime_error("Null CAD shape");
    std::vector<TopoDS_Shape> solids;
    for (TopExp_Explorer it(shape, TopAbs_SOLID); it.More(); it.Next()) solids.push_back(it.Current());
    if (solids.empty()) throw std::runtime_error("CAD has no solid");
    if (argc > 2 && std::string(argv[2]) == "--stats") {
      Bnd_Box box;
      BRepBndLib::AddOptimal(shape, box, false, true);
      double x0,y0,z0,x1,y1,z1; box.Get(x0,y0,z0,x1,y1,z1);
      GProp_GProps prop; BRepGProp::VolumeProperties(shape, prop);
      int faces = 0; for (TopExp_Explorer it(shape, TopAbs_FACE); it.More(); it.Next()) ++faces;
      std::cout << std::setprecision(17) << "{\"solids\":" << solids.size()
                << ",\"faces\":" << faces << ",\"volume\":" << prop.Mass()
                << ",\"optimal_bounds\":[" << x0 << ',' << y0 << ',' << z0 << ',' << x1 << ',' << y1 << ',' << z1
                << "],\"bound_method\":\"OCCT8 BRepBndLib::AddOptimal(false,true)\"}\n";
      return 0;
    }
    const double tol = argc > 2 ? std::stod(argv[2]) : 1e-7;
    if (!(tol > 0)) throw std::runtime_error("Tolerance must be positive");
    std::vector<std::unique_ptr<BRepClass3d_SolidClassifier>> classifiers;
    for (const auto& solid : solids) classifiers.emplace_back(new BRepClass3d_SolidClassifier(solid));
    std::cerr << "{\"ready\":true,\"solid_count\":" << solids.size() << ",\"tolerance\":" << tol << "}\n";
    double x,y,z; size_t count = 0;
    while (std::cin >> x >> y >> z) {
      int state = 0; // OUT=0, IN=1, ON=2, UNKNOWN=-1. ON is explicit.
      for (auto& classifier : classifiers) {
        classifier->Perform(gp_Pnt(x,y,z), tol);
        if (classifier->State() == TopAbs_IN) { state = 1; break; }
        if (classifier->State() == TopAbs_ON) state = 2;
        else if (classifier->State() == TopAbs_UNKNOWN && state == 0) state = -1;
      }
      std::cout << state << std::endl;
      ++count;
    }
    const double sec = std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
    std::cerr << "{\"queries\":" << count << ",\"seconds_including_load\":" << sec << "}\n";
    return 0;
  } catch (const Standard_Failure& e) { std::cerr << "OCCT failure: " << e.GetMessageString() << '\n'; return 3; }
    catch (const std::exception& e) { std::cerr << "Failure: " << e.what() << '\n'; return 4; }
}
