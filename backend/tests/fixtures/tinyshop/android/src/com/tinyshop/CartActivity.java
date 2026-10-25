package com.tinyshop;

import java.util.ArrayList;
import java.util.List;

/** Android screen listing the items in the cart. */
public class CartActivity {
    private final List<String> skus = new ArrayList<>();

    /** Called when the user taps "remove" next to an item. */
    public void onRemoveClicked(String sku) {
        skus.remove(sku);
        refreshList();
    }

    private void refreshList() {
        System.out.println("cart now has " + skus.size() + " items");
    }
}
