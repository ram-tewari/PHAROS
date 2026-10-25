#include <cmath>
#include <vector>

namespace shipping {

// A parcel's outer dimensions in centimetres.
struct Parcel {
    double width, height, depth;
};

// Volumetric weight in kg as charged by couriers (L*W*H / 5000).
double volumetric_weight(const Parcel& p) {
    return p.width * p.height * p.depth / 5000.0;
}

// Total billable weight: the larger of actual and volumetric weight per parcel.
double billable_weight(const std::vector<Parcel>& parcels, const std::vector<double>& actual) {
    double total = 0;
    for (size_t i = 0; i < parcels.size(); ++i) {
        total += std::fmax(actual[i], volumetric_weight(parcels[i]));
    }
    return total;
}

}  // namespace shipping
