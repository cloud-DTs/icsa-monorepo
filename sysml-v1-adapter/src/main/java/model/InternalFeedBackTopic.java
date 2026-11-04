package model;

public class InternalFeedBackTopic extends  FeedBack{


    public String getShortenTopic(){
        return TwinIdentity.getShortenUUID(this.getTopic());
    }
}
