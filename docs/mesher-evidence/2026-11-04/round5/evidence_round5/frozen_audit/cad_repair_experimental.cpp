// Round4 exact CAD queries. Existing solids only; no healing or Boolean edits.
#include <BRep_Builder.hxx>
#include <ShapeFix_Shape.hxx>
#include <BRepCheck_Analyzer.hxx>
#include <BRepCheck_Result.hxx>
#include <BRepMesh_IncrementalMesh.hxx>
#include <StlAPI_Writer.hxx>
#include <TopoDS.hxx>
#include <TopTools_IndexedMapOfShape.hxx>
#include <TopExp.hxx>
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
    if (argc > 4 && std::string(argv[2]) == "--repair") {
      const double maximum_tolerance = std::stod(argv[3]);
      ShapeFix_Shape fixer(shape); fixer.SetPrecision(1e-7); fixer.SetMinTolerance(1e-7); fixer.SetMaxTolerance(maximum_tolerance);
      const bool changed = fixer.Perform(); const TopoDS_Shape result = fixer.Shape();
      if(!BRepTools::Write(result,argv[4])) throw std::runtime_error("Repaired BREP write failed");
      BRepCheck_Analyzer before(shape,true,false),after(result,true,false);
      GProp_GProps p0,p1; BRepGProp::VolumeProperties(shape,p0); BRepGProp::VolumeProperties(result,p1);
      std::cout << std::setprecision(17) << "{\"operation\":\"ShapeFix_Shape Perform\",\"changed_flag\":" << (changed?"true":"false")
        << ",\"max_tolerance_mm\":" << maximum_tolerance << ",\"precision_mm\":1e-7,\"valid_before\":" << (before.IsValid()?"true":"false")
        << ",\"valid_after\":" << (after.IsValid()?"true":"false") << ",\"volume_before\":" << p0.Mass() << ",\"volume_after\":" << p1.Mass() << "}\n";
      return 0;
    }
    if (argc > 5 && std::string(argv[2]) == "--select") {
      const int wanted_faces = std::stoi(argv[3]);
      const double wanted_volume = std::stod(argv[4]);
      int matches = 0, index = 0, selected_index = 0;
      TopoDS_Shape selected;
      for (const auto& solid : solids) {
        ++index;
        int faces = 0; for (TopExp_Explorer it(solid, TopAbs_FACE); it.More(); it.Next()) ++faces;
        GProp_GProps prop; BRepGProp::VolumeProperties(solid, prop);
        if (faces == wanted_faces && std::abs(prop.Mass()/wanted_volume-1) < 1e-7) {
          selected = solid; selected_index = index; ++matches;
        }
      }
      if (matches != 1) throw std::runtime_error("Expected unique face-count and volume match; got " + std::to_string(matches));
      if (!BRepTools::Write(selected, argv[5])) throw std::runtime_error("BREP output failed");
      std::cout << "{\"matches\":1,\"assembly_solids\":" << solids.size() << ",\"selected_native_index\":" << selected_index
                << ",\"faces\":" << wanted_faces << ",\"healing\":false,\"defeaturing\":false}\n";
      return 0;
    }
    if (argc > 2 && std::string(argv[2]) == "--validity") {
      BRepCheck_Analyzer analyzer(shape, true, false);
      TopTools_IndexedMapOfShape entities; TopExp::MapShapes(shape, entities);
      int invalid_subshapes = 0; int invalid_faces = 0, invalid_edges = 0;
      for (int i=1; i<=entities.Extent(); ++i) {
        if (!analyzer.IsValid(entities(i))) { ++invalid_subshapes;
          if(entities(i).ShapeType()==TopAbs_FACE) ++invalid_faces;
          if(entities(i).ShapeType()==TopAbs_EDGE) ++invalid_edges;
        }
      }
      std::cout << "{\"nonzero_statuses\":[";
      bool first = true;
      for (int i=1; i<=entities.Extent(); ++i) {
        const auto result = analyzer.Result(entities(i)); if(result.IsNull()) continue;
        auto emit = [&](const NCollection_List<BRepCheck_Status>& statuses, int context) {
          for (auto it = statuses.cbegin(); it != statuses.cend(); ++it) if(*it != BRepCheck_NoError) {
            if(!first) std::cout << ','; first=false;
            std::cout << "{\"shape_index\":" << i << ",\"shape_type\":" << int(entities(i).ShapeType())
                      << ",\"context_index\":" << context << ",\"status_code\":" << int(*it) << '}';
          }
        };
        emit(result->Status(),0);
        for(result->InitContextIterator(); result->MoreShapeInContext(); result->NextShapeInContext())
          emit(result->StatusOnShape(),entities.FindIndex(result->ContextualShape()));
      }
      std::cout << "],\"valid\":" << (analyzer.IsValid() ? "true" : "false")
        << ",\"invalid_subshapes_including_parent_containers\":" << invalid_subshapes
        << ",\"invalid_faces\":" << invalid_faces << ",\"invalid_edges\":" << invalid_edges
        << ",\"geometric_controls\":true,\"parallel\":false,\"method\":\"OCCT8 BRepCheck_Analyzer\"}\n";
      return 0;
    }
    if (argc > 4 && std::string(argv[2]) == "--tessellate") {
      const double deflection = std::stod(argv[3]);
      BRepMesh_IncrementalMesh mesher(shape, deflection, false, 0.35, false);
      if(!mesher.IsDone()) throw std::runtime_error("BRepMesh not done");
      StlAPI_Writer writer; writer.ASCIIMode() = false;
      if(!writer.Write(shape, argv[4])) throw std::runtime_error("STL output failed");
      std::cout << "{\"success\":true,\"deflection\":" << deflection
        << ",\"angular_deflection\":0.35,\"relative\":false,\"parallel\":false,\"status_flags\":" << mesher.GetStatusFlags() << "}\n";
      return 0;
    }
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
