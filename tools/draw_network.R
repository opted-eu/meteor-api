library(igraph)
library(readr)
library(dplyr)

df <- read_csv('edge_list.csv')
network <- graph_from_data_frame(d=df, directed=TRUE) 

resources <- c('Archive', 'Dataset',
                'Collection', 'LearningMaterial',
                'ScientificPublication', 'Tool')

actors <- c('Government', 'JournalisticBrand',
            'NewsSource', 'Organization',
            'Parliament', 'Person',
            'PoliticalParty')

V(network)$type <- case_match(V(network)$name,
                             resources ~ "Resource",
                             actors ~ "Actors & Institutions",
                             .default = "Linking Entities")


# Make a palette of 3 colors
library(RColorBrewer)
coul  <- brewer.pal(3, "Set2") 
 
# Create a vector of color
my_color <- coul[as.numeric(as.factor(V(network)$type))]

png("schema.png", 
    width = 1920, 
    height = 1080, 
    units = "px",
    pointsize = 18,
    bg = NA)

plot(network, 
     layout = layout_with_lgl(network),
     edge.arrow.size = 0.5,
     edge.label = NA,
     vertex.label.family = 'sans',
     vertex.color = my_color,
     main = "Entity Relationships in Meteor")

legend("bottomleft", 
        legend=levels(as.factor(V(network)$type)),
        col = coul , 
        bty = "n", 
        pch=20 , 
        pt.cex = 3,
        cex = 1.5, 
        text.col=coul , 
        horiz = FALSE, 
        inset = c(0.1, 0.1))

dev.off()
