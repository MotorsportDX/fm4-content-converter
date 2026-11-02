// SPDX-License-Identifier: GPL-3.0-only
// Local extension of the pinned ForzaEditor FM3 -> FM4 section conversion,
// applied by build_carbin_cpu.py (see PATCHES there).
//
// FM4 encodes a vertex as a direction and a length relative to the section's
// bounds, the length clamped to the half diagonal. Some FM3 sections hold
// vertices outside their own bounds (|q| up to 4.1 on FER_30_333SP_98 lexanRF,
// 1.59 on AUD_A4Touring_08 glassLR), which the unpatched converter clamps by up
// to 0.45 m. Such a section is given bounds fitted to its vertices instead,
// the game's convention (AABB centre, symmetric extents, see Reencode).
namespace ForzaStudio
{
    using System;

    public partial class CarbinModel
    {
        private static bool ExceedsBounds(Section section, double[] lod, double[] lod0)
        {
            double scale = Scale(section.Bounds);
            foreach (double[] positions in new double[][] { lod, lod0 })
            {
                for (int i = 0; i + 2 < positions.Length; i += 3)
                {
                    double length = 0;
                    for (int c = 0; c < 3; c++)
                    {
                        double center = (section.Bounds[3 + c] + section.Bounds[6 + c]) / 2;
                        double q = (positions[i + c] - section.Bounds[c] - center) / scale;
                        length += q * q;
                    }
                    if (Math.Sqrt(length) > 1.0)
                    {
                        return true;
                    }
                }
            }
            return false;
        }

        private static void FitBounds(Section section, double[] lod, double[] lod0)
        {
            double[] min = { double.MaxValue, double.MaxValue, double.MaxValue };
            double[] max = { double.MinValue, double.MinValue, double.MinValue };
            foreach (double[] positions in new double[][] { lod, lod0 })
            {
                for (int i = 0; i < positions.Length; i++)
                {
                    min[i % 3] = Math.Min(min[i % 3], positions[i]);
                    max[i % 3] = Math.Max(max[i % 3], positions[i]);
                }
            }
            float[] origin;
            float[] half;
            SymmetricBounds(min, max, out origin, out half);
            for (int c = 0; c < 3; c++)
            {
                section.Bounds[c] = origin[c];
                section.Bounds[3 + c] = -half[c];
                section.Bounds[6 + c] = half[c];
            }
        }
    }
}
