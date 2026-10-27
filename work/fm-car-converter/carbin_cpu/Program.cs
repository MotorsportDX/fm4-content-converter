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

    private static int Main(string[] args)
    {
        try
        {
            if (args.Length < 2 || (args[0] != "inspect" && args[0] != "convert"))
                throw new ArgumentException("Usage: carbin-cpu inspect INPUT | convert INPUT OUTPUT");
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
