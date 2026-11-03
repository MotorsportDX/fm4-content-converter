// SPDX-License-Identifier: GPL-3.0-only
// CPU-only adapter for FMdangaina/ForzaEditor, pinned by build_carbin_cpu.py.
// Only CarbinModel, its FM3 converter, and ObjMesh are linked. No editor,
// renderer, game, graphics device, texture encoder, or native library is started.
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Web.Script.Serialization;
using ForzaStudio;

namespace ForzaStudio
{
    // ObjMesh's optional MTL export is outside this adapter. Do not link the
    // editor Utilities class (which also knows about rendering and native IO).
    internal static class Utilities
    {
        public static Microsoft.Xna.Framework.Color GetRandomColor(int seed)
        {
            throw new NotSupportedException("MTL export is disabled in the CPU adapter");
        }
    }
}

internal static class Program
{
    private static string Hash(byte[] b)
    {
        using (var h = SHA256.Create())
            return BitConverter.ToString(h.ComputeHash(b)).Replace("-", "").ToLowerInvariant();
    }

    private static object Describe(CarbinModel m)
    {
        m.CheckDrawLists();
        return new {
            family = m.IsMotorsport3 ? "FM3" : m.IsHorizon ? "FH" : "FM4",
            type = m.Type, header_bytes = m.Head.Length, trailer_bytes = m.Trailer.Length,
            sections = m.Sections.Select(s => new {
                name = s.Name, bounds = s.Bounds,
                lod_count = s.Lod.Count, lod_stride = s.Lod.Stride,
                lod0_count = s.Lod0.Count, lod0_stride = s.Lod0.Stride,
                damage_lod_count = s.DamageLod.Count, damage_lod_stride = s.DamageLod.Stride,
                damage_lod0_count = s.DamageLod0.Count, damage_lod0_stride = s.DamageLod0.Stride,
                meshes = s.SubSections.Select(t => new {
                    name = t.Name, lod = t.Lod, primitive = t.IndexType,
                    index_count = t.Indices.Count, index_size = t.IndexSize, uv = t.Uv
                }).ToArray()
            }).ToArray()
        };
    }

    // FM4 mirror materials (mirrorLeft/Right/Middle) show the mirror image over UV 0..1, with U
    // rising with model X and V with model Y (798 of the 830 LOD 0 mirror meshes of the 305 FM4
    // Disc 1 cockpits). A mesh renamed to one keeps its source UVs, which index a small atlas patch.
    // When no other mesh of the part uses its vertices, their UV0 is written from X and Y directly
    // (transform 0,1,0,1); otherwise the per-mesh UV transform is refitted, which needs the source
    // UVs to be affine in X and Y. Returns the worst residual in UV units (0 when written directly).
    private static double FitMirrorUv(CarbinModel.Section section, CarbinModel.SubSection sub)
    {
        CarbinModel.VertexBuffer buffer = sub.Lod == 0 ? section.Lod0 : section.Lod;
        double[] positions = CarbinModel.Positions(section, buffer);
        var used = new HashSet<int>(CarbinModel.StripTriangles(sub).SelectMany(t => t)).ToList();
        if (used.Count == 0)
            throw new InvalidDataException("Mirror mesh " + sub.Name + " has no triangles");
        bool shared = section.SubSections.Where(s => s != sub && (s.Lod == 0) == (sub.Lod == 0))
            .SelectMany(s => CarbinModel.StripTriangles(s).SelectMany(t => t)).Any(v => used.Contains(v));
        if (!shared)
        {
            for (int axis = 0; axis < 2; axis++)
            {
                double low = used.Min(v => positions[v * 3 + axis]);
                double span = used.Max(v => positions[v * 3 + axis]) - low;
                if (span <= 1e-6)
                    throw new InvalidDataException("Mirror mesh " + sub.Name + " is flat along axis " + axis);
                foreach (int v in used)
                {
                    int raw = (int) Math.Round((positions[v * 3 + axis] - low) / span * 65535);
                    buffer.Data[v * buffer.Stride + 8 + 2 * axis] = (byte) (raw >> 8);
                    buffer.Data[v * buffer.Stride + 9 + 2 * axis] = (byte) raw;
                }
                sub.Uv[2 * axis] = 0;
                sub.Uv[2 * axis + 1] = 1;
            }
            return 0;
        }
        double worst = 0;
        for (int axis = 0; axis < 2; axis++)
        {
            double[] raw = used.Select(v => (double) ((buffer.Data[v * buffer.Stride + 8 + 2 * axis] << 8)
                | buffer.Data[v * buffer.Stride + 9 + 2 * axis]) / 65535.0).ToArray();
            double[] p = used.Select(v => positions[v * 3 + axis]).ToArray();
            double low = p.Min(), span = p.Max() - low;
            if (span <= 1e-6)
                throw new InvalidDataException("Mirror mesh " + sub.Name + " is flat along axis " + axis);
            double[] target = p.Select(x => (x - low) / span).ToArray();
            double mr = raw.Average(), mt = target.Average();
            double sxx = raw.Sum(r => (r - mr) * (r - mr));
            if (sxx <= 1e-12)
                throw new InvalidDataException("Mirror mesh " + sub.Name + " has constant UVs");
            double slope = raw.Zip(target, (r, t) => (r - mr) * (t - mt)).Sum() / sxx;
            double offset = mt - slope * mr;
            worst = Math.Max(worst, raw.Zip(target, (r, t) => Math.Abs(offset + slope * r - t)).Max());
            sub.Uv[2 * axis] = (float) offset;
            sub.Uv[2 * axis + 1] = (float) slope;
        }
        if (worst > 0.05)
            throw new InvalidDataException("Mirror mesh " + sub.Name + " UVs are not affine in X/Y (" + worst + ")");
        return worst;
    }

    private static int Main(string[] args)
    {
        try
        {
            if (args.Length < 2 || (args[0] != "inspect" && args[0] != "convert" && args[0] != "closeup" && args[0] != "lod0"))
                throw new ArgumentException("Usage: carbin-cpu inspect INPUT | convert INPUT OUTPUT"
                    + " | closeup INPUT HEAD OUTPUT SECTIONS include|exclude [MATERIALS] | lod0 INPUT OUTPUT");
            byte[] source = File.ReadAllBytes(args[1]);
            var model = new CarbinModel(source, true);
            if (!source.SequenceEqual(model.ToBytes()))
                throw new InvalidDataException("Source parse/write did not round-trip byte for byte");
            object before = Describe(model);
            if (args[0] == "inspect")
            {
                Console.WriteLine(new JavaScriptSerializer().Serialize(before));
                return 0;
            }
            if (args[0] == "closeup")
            {
                // A _lod0 or _cockpit file from an FM4 main model's LOD 1. HEAD is a native file of the
                // wanted kind (its header is used as is); SECTIONS lists one section name per line.
                // MATERIALS (optional) holds "old new" material renames, one per line, for the close-up's
                // meshes: FM4 maps LOD 0 cockpit meshes to cockpit_<material> techniques. "section/old new"
                // renames only in that section and takes precedence over a plain "old new".
                if ((args.Length != 6 && args.Length != 7) || model.IsMotorsport3 || model.IsHorizon || model.Type != 2
                    || (args[5] != "include" && args[5] != "exclude"))
                    throw new ArgumentException("closeup requires an FM4 car model, a head file, a new output,"
                        + " a section list, include|exclude and optionally a material rename list");
                var renames = new Dictionary<string, string>();
                foreach (string line in args.Length == 7 ? File.ReadAllLines(args[6]) : new string[0])
                {
                    string[] pair = line.Split(new[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
                    if (pair.Length == 0)
                        continue;
                    if (pair.Length != 2 || renames.ContainsKey(pair[0]) || pair.Any(n => n.Any(ch => ch < 33 || ch > 126)))
                        throw new ArgumentException("Material renames need one 'old new' ASCII pair per line");
                    renames.Add(pair[0], pair[1]);
                }
                byte[] headSource = File.ReadAllBytes(args[2]);
                var headModel = new CarbinModel(headSource);
                if (headModel.Type != 2 || !headSource.SequenceEqual(headModel.ToBytes()))
                    throw new InvalidDataException("Head file is not a round-trippable FM4 car model");
                var names = new HashSet<string>(File.ReadAllLines(args[4]).Select(l => l.Trim()).Where(l => l.Length > 0));
                bool include = args[5] == "include";
                CarbinModel closeUp = model.CloseUpFromLod1(headModel.Head, name => names.Contains(name) == include);
                var renamed = new Dictionary<string, int>();
                var mirrorFits = new Dictionary<string, double>();
                foreach (var section in closeUp.Sections)
                    foreach (var sub in section.SubSections)
                    {
                        string key = section.Name + "/" + sub.Name, target;
                        if (!renames.TryGetValue(key, out target))
                        {
                            key = sub.Name;
                            if (!renames.TryGetValue(key, out target))
                                continue;
                        }
                        renamed[key] = (renamed.ContainsKey(key) ? renamed[key] : 0) + 1;
                        sub.Name = target;
                        if (target == "mirrorLeft" || target == "mirrorRight" || target == "mirrorMiddle")
                            mirrorFits[section.Name + "/" + target] = FitMirrorUv(section, sub);
                    }
                var unused = renames.Keys.Where(k => !renamed.ContainsKey(k)).ToArray();
                if (unused.Length > 0)
                    throw new ArgumentException("Material renames matched no mesh: " + string.Join(", ", unused));
                byte[] written = closeUp.ToBytes();
                var check = new CarbinModel(written);
                if (check.IsHorizon || !written.SequenceEqual(check.ToBytes()))
                    throw new InvalidDataException("Close-up model is not a round-trippable FM4 model");
                using (var file = new FileStream(args[3], FileMode.CreateNew, FileAccess.Write))
                    file.Write(written, 0, written.Length);
                Console.WriteLine(new JavaScriptSerializer().Serialize(new {
                    input_sha256 = Hash(source), head_sha256 = Hash(headSource), output_sha256 = Hash(written),
                    source = before, target = Describe(check), renamed_meshes = renamed,
                    mirror_uv_fit_residual = mirrorFits, runtime_tested = false
                }));
                return 0;
            }
            if (args[0] == "lod0")
            {
                // LOD 0 of an FM4 wheel (type 3) rebuilt from its LOD 1, for sources without one (FM2
                // wheels). As FM4's own wheels (441 of 442), LOD 0 draws no tire.
                if (args.Length != 3 || model.IsMotorsport3 || model.IsHorizon || model.Type != 3)
                    throw new ArgumentException("lod0 requires an FM4 wheel model and a new output");
                if (model.Sections.Any(s => s.SubSections.Any(t => t.Lod == 0)))
                    throw new InvalidDataException("The wheel already has LOD 0 meshes");
                if (!model.Lod0FromLod1(name => name != "tire"))
                    throw new InvalidDataException("The wheel has no LOD 1 to copy");
                byte[] written = model.ToBytes();
                var check = new CarbinModel(written);
                if (check.IsHorizon || check.Type != 3 || !written.SequenceEqual(check.ToBytes()))
                    throw new InvalidDataException("Rebuilt wheel is not a round-trippable FM4 model");
                using (var file = new FileStream(args[2], FileMode.CreateNew, FileAccess.Write))
                    file.Write(written, 0, written.Length);
                Console.WriteLine(new JavaScriptSerializer().Serialize(new {
                    input_sha256 = Hash(source), output_sha256 = Hash(written),
                    source = before, target = Describe(check), runtime_tested = false
                }));
                return 0;
            }
            if (args.Length != 3 || !model.IsMotorsport3)
                throw new ArgumentException("Conversion requires an FM3 input and a new output path");
            string conversion = model.ConvertMotorsport3ToMotorsport4();
            byte[] converted = model.ToBytes();
            var reparsed = new CarbinModel(converted);
            if (reparsed.IsMotorsport3 || reparsed.IsHorizon ||
                !converted.SequenceEqual(reparsed.ToBytes()))
                throw new InvalidDataException("Target is not a round-trippable FM4 model");
            object after = Describe(reparsed);
            using (var file = new FileStream(args[2], FileMode.CreateNew, FileAccess.Write))
                file.Write(converted, 0, converted.Length);
            Console.WriteLine(new JavaScriptSerializer().Serialize(new {
                input_sha256 = Hash(source), output_sha256 = Hash(converted),
                source = before, target = after, conversion = conversion,
                runtime_tested = false
            }));
            return 0;
        }
        catch (Exception e)
        {
            Console.Error.WriteLine(e.GetType().Name + ": " + e.Message);
            return 1;
        }
    }
}
