using System;
using System.Globalization;
using Avalonia.Data.Converters;
using Avalonia;

namespace QuiverLauncher
{
    /// <summary>The same margin on all four sides, from a whole number of pixels.</summary>
    public sealed class UniformThicknessConverter : IValueConverter
    {
        public static readonly UniformThicknessConverter Instance = new();

        public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture) =>
            value is int pixels ? new Thickness(pixels) : new Thickness(0);

        public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
            throw new NotSupportedException();
    }

    public class ThicknessConverter : IValueConverter
    {
        public static readonly ThicknessConverter Instance = new();

        public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        {
            if (value is double doubleValue)
            {
                return new Thickness(doubleValue, 0, 0, 0);
            }
            if (value is int intValue)
            {
                return new Thickness(intValue, 0, 0, 0);
            }
            return new Thickness(0);
        }

        public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        {
            throw new NotImplementedException();
        }
    }
}