<?xml version="1.0" encoding="utf-8"?>
<!-- Empire ports can build the galleass (added once, after NavalDLC's own hull list). -->
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output omit-xml-declaration="no" indent="yes" />
  <xsl:template match="@*|node()">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()" />
    </xsl:copy>
  </xsl:template>
  <xsl:template match="Culture[@id='empire']/available_ship_hulls[not(ship_hull[@id='ShipHull.empire_galleass'])]">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()" />
      <ship_hull id="ShipHull.empire_galleass" />
    </xsl:copy>
  </xsl:template>
</xsl:stylesheet>
