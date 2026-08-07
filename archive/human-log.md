## copied ID revamp
We already did a great job in reducing the ID overhead from 27% to 10%
We achieved this by going from composite id to 8character hex IDs
Let me ask an interesting question
the characters we are storing and you are reading are utf-8 I guess
So we can encode **much more** in a character than 16 varants (hex ID)
I get that using the full utf-8 character table migh cause ambiguities
but is there an extended alphabet over 16 so we can shorten the ids even more?
I think case sensitive is not a good idea here so Id go for case insensitive
but A-Z + 0-9 + (some specials) + (others from utf table)
I think we can go down to 4 character with this

## Conversations are almost breaking the djot format?
I feel that the conversations are almost toolong for the djot format
as you noted earlier in a conversation it is routine to emit the fencing characters (`:::` if i recall correctly) so it can't be made sure that a tool use output doesn1t break the system
regardloss of our effort?
If this is true (at least partially or there is a risk) maybe we should have one djot per turn and assemble only in HTML?
I don't want the shource of truth to be fragile

## Obsidian style frontmatter
I'm heavily debating this and I think I'm going to implement this

## Conversations don't have to be named automatically
- the user can have a chance to name them in the meta


